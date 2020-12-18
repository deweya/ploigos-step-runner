"""`StepImplementer` for the `uat` step using Maven driving Selenium generating Cucumber reports.

Step Configuration
------------------
Step configuration expected as input to this step.
Could come from:
* static configuration
* runtime configuration
* previous step results

Configuration Key    | Required? | Default            | Description
---------------------|-----------|--------------------|------------
`fail-on-no-tests`   | Yes       | True               | Value to specify whether unit-test \
                                                        step can succeed when no tests are defined
`pom-file`           | Yes       | `pom.xml`          | pom used to run tests and check \
                                                        for existence of custom reportsDirectory
`selenium-hub-url`   | Yes       |                    | URL where the Selenium Hub is running
`target-host-url`    | Maybe     |                    | Target host URL for UAT. \
                                                        <br/> \
                                                        If not given then use first host url from \
                                                        `deployed-host-urls`.
`deployed-host-urls` | Maybe     |                    | Deployed host URLs. If `target-host-url` \
                                                        is not given then use first URL from this \
                                                        list. If `target-host-url` is given then \
                                                        ignore this value.
`uat-maven-profile`  | Yes       | `integration-test` | Maven profile to use to invoke \
                                                        Selenium tests.

Result Artifacts
----------------
Results artifacts output by this step.

Result Artifact Key    | Description
-----------------------|------------
`maven-output`         | Path to Stdout and Stderr from invoking Maven.
`surefire-reports`     | Path to Surefire reports generated by Maven.
`cucumber-report-html` | Path to Cucumber HTML report generated by Maven.
`cucumber-report-json` | Path to Cucumber JSON report generated by Maven.
"""
import os
import sys

import sh
from ploigos_step_runner.config.config_value import ConfigValue
from ploigos_step_runner.exceptions import StepRunnerException
from ploigos_step_runner.step_implementers.shared.maven_generic import MavenGeneric
from ploigos_step_runner.step_result import StepResult
from ploigos_step_runner.utils.io import create_sh_redirect_to_multiple_streams_fn_callback

DEFAULT_CONFIG = {
    'fail-on-no-tests': True,
    'pom-file': 'pom.xml',
    'uat-maven-profile': 'integration-test'
}

REQUIRED_CONFIG_OR_PREVIOUS_STEP_RESULT_ARTIFACT_KEYS = [
    'fail-on-no-tests',
    'pom-file',
    'selenium-hub-url',
    'uat-maven-profile'
]


class MavenSeleniumCucumber(MavenGeneric):
    """`StepImplementer` for the `uat` step using Maven driving Selenium generating
    Cucumber reports.
    """

    @staticmethod
    def step_implementer_config_defaults():
        """Getter for the StepImplementer's configuration defaults.

        Returns
        -------
        dict
            Default values to use for step configuration values.

        Notes
        -----
        These are the lowest precedence configuration values.
        """
        return DEFAULT_CONFIG

    @staticmethod
    def _required_config_or_result_keys():
        """Getter for step configuration or previous step result artifacts that are required before
        running this step.

        See Also
        --------
        _validate_required_config_or_previous_step_result_artifact_keys

        Returns
        -------
        array_list
            Array of configuration keys or previous step result artifacts
            that are required before running the step.
        """
        return REQUIRED_CONFIG_OR_PREVIOUS_STEP_RESULT_ARTIFACT_KEYS

    def _validate_required_config_or_previous_step_result_artifact_keys(self):
        """Validates that the required configuration keys or previous step result artifacts
        are set and have valid values.

        Validates that:
        * required configuration is given
        * either target-host-url or deployed-host-urls is given

        Raises
        ------
        StepRunnerException
            If step configuration or previous step result artifacts have invalid required values
        """
        super()._validate_required_config_or_previous_step_result_artifact_keys()

        # target-host-url or deployed-host-urls must be supplied
        target_host_url = self.get_value('target-host-url')
        deployed_host_urls = self.get_value('deployed-host-urls')
        if (not target_host_url) and (not deployed_host_urls):
            raise StepRunnerException(
                "Either 'target-host-url' or 'deployed-host-urls' needs to be supplied but"
                " neither were."
            )

    def _run_step(self): # pylint: disable=too-many-locals
        """Runs the step implemented by this StepImplementer.

        Returns
        -------
        StepResult
            Object containing the dictionary results of this step.
        """
        step_result = StepResult.from_step_implementer(self)

        settings_file = self._generate_maven_settings()
        pom_file = self.get_value('pom-file')
        fail_on_no_tests = self.get_value('fail-on-no-tests')
        selenium_hub_url = self.get_value('selenium-hub-url')
        deployed_host_urls = ConfigValue.convert_leaves_to_values(
            self.get_value('deployed-host-urls')
        )
        uat_maven_profile = self.get_value('uat-maven-profile')

        # NOTE:
        #   at some point may need to do smarter logic if a deployable has more then one deployed
        #   host URL to do UAT against all of them, but for now, use first one as target of UAT
        if isinstance(deployed_host_urls, list):
            target_base_url = deployed_host_urls[0]
            if len(deployed_host_urls) > 1:
                step_result.message = \
                    f"Given more then one deployed host URL ({deployed_host_urls})," \
                    f" targeting first one ({target_base_url}) for user acceptance test (UAT)."
                print(step_result.message)
        elif deployed_host_urls:
            target_base_url = deployed_host_urls
        else:
            target_base_url = self.get_value('target-host-url')


        # ensure surefire plugin enabled
        maven_surefire_plugin = self._get_effective_pom_element(
            element_path=MavenGeneric.SUREFIRE_PLUGIN_XML_ELEMENT_PATH
        )
        if maven_surefire_plugin is None:
            step_result.success = False
            step_result.message = 'Unit test dependency "maven-surefire-plugin" ' \
                f'missing from effective pom ({self._get_effective_pom()}).'
            return step_result

        # get surefire test results dir
        reports_dir = self._get_effective_pom_element(
            element_path=MavenGeneric.SUREFIRE_PLUGIN_REPORTS_DIR_XML_ELEMENT_PATH
        )
        if reports_dir is not None:
            test_results_dir = reports_dir.text
        else:
            test_results_dir = os.path.join(
                os.path.dirname(os.path.abspath(pom_file)),
                MavenGeneric.DEFAULT_SUREFIRE_PLUGIN_REPORTS_DIR
            )

        cucumber_html_report_path = os.path.join(self.work_dir_path, 'cucumber.html')
        cucumber_json_report_path = os.path.join(self.work_dir_path, 'cucumber.json')
        mvn_output_file_path = self.write_working_file('mvn_test_output.txt')
        try:
            with open(mvn_output_file_path, 'w') as mvn_output_file:
                out_callback = create_sh_redirect_to_multiple_streams_fn_callback([
                    sys.stdout,
                    mvn_output_file
                ])
                err_callback = create_sh_redirect_to_multiple_streams_fn_callback([
                    sys.stderr,
                    mvn_output_file
                ])
                sh.mvn( # pylint: disable=no-member
                    'clean',
                    'test',
                    f'-P{uat_maven_profile}',
                    f'-Dselenium.hub.url={selenium_hub_url}',
                    f'-Dtarget.base.url={target_base_url}',
                    f'-Dcucumber.plugin=' \
                        f'html:{cucumber_html_report_path},' \
                        f'json:{cucumber_json_report_path}',
                    '-f', pom_file,
                    '-s', settings_file,
                    _out=out_callback,
                    _err=err_callback
                )

            if not os.path.isdir(test_results_dir) or len(os.listdir(test_results_dir)) == 0:
                if fail_on_no_tests:
                    step_result.message = "No user acceptance tests defined" \
                        f" using maven profile ({uat_maven_profile})."
                    step_result.success = False
                else:
                    step_result.message = "No user acceptance tests defined" \
                        f" using maven profile ({uat_maven_profile})," \
                        " but 'fail-on-no-tests' is False."
        except sh.ErrorReturnCode:
            step_result.message = "User acceptance test failures. See 'maven-output'" \
                ", 'surefire-reports', 'cucumber-report-html', and 'cucumber-report-json'" \
                " report artifacts for details."
            step_result.success = False

        step_result.add_artifact(
            description=f"Standard out and standard error by 'mvn -P{uat_maven_profile} test'.",
            name='maven-output',
            value=mvn_output_file_path
        )
        step_result.add_artifact(
            description=f"Surefire reports generated by 'mvn -P{uat_maven_profile} test'.",
            name='surefire-reports',
            value=test_results_dir
        )
        step_result.add_artifact(
            description=f"Cucumber (HTML) report generated by 'mvn -P{uat_maven_profile} test'.",
            name='cucumber-report-html',
            value=cucumber_html_report_path
        )
        step_result.add_artifact(
            description=f"Cucumber (JSON) report generated by 'mvn -P{uat_maven_profile} test'.",
            name='cucumber-report-json',
            value=cucumber_json_report_path
        )

        return step_result
