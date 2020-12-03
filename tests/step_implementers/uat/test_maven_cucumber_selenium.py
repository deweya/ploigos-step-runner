import os
from io import IOBase
from shutil import copyfile
from unittest.mock import patch

import sh
from testfixtures import TempDirectory
from tests.helpers.maven_step_implementer_test_case import \
    MaveStepImplementerTestCase
from tests.helpers.test_utils import Any
from tssc.step_implementers.uat import MavenCucumberSelenium
from tssc.step_result import StepResult
from tssc.utils.file import create_parent_dir


class TestStepImplementerMavenCucumberSelenium(MaveStepImplementerTestCase):
    def create_step_implementer(
            self,
            step_config={},
            results_dir_path='',
            results_file_name='',
            work_dir_path=''
    ):
        return self.create_given_step_implementer(
            step_implementer=MavenCucumberSelenium,
            step_config=step_config,
            step_name='uat',
            implementer='MavenCucumberSelenium',
            results_dir_path=results_dir_path,
            results_file_name=results_file_name,
            work_dir_path=work_dir_path
        )

    def test_step_implementer_config_defaults(self):
        actual_defaults = MavenCucumberSelenium.step_implementer_config_defaults()
        expected_defaults = {
            'fail-on-no-tests': True,
            'pom-file': 'pom.xml',
            'uat-maven-profile': 'integration-test'
        }
        self.assertEqual(expected_defaults, actual_defaults)

    def test__required_config_or_result_keys(self):
        actual_required_keys = MavenCucumberSelenium._required_config_or_result_keys()
        expected_required_keys = [
            'fail-on-no-tests',
            'pom-file',
            'selenium-hub-url',
            'uat-maven-profile'
        ]
        self.assertEqual(expected_required_keys, actual_required_keys)

    def __run__run_step_test(
        self,
        test_dir,
        mvn_mock,
        write_effective_pom_mock,
        generate_maven_settings_mock,
        pom_content,
        group_id,
        artifact_id,
        surefire_reports_dir,
        selenium_hub_url,
        target_base_url=None,
        write_mock_test_results=True,
        assert_mvn_called=True,
        assert_report_artifact=True,
        expected_result_success=True,
        expected_result_message='',
        fail_on_no_tests=None,
        uat_maven_profile=None,
        pom_file_name='pom.xml',
        raise_error_on_tests=False
    ):
        results_dir_path = os.path.join(test_dir.path, 'tssc-results')
        results_file_name = 'tssc-results.yml'
        work_dir_path = os.path.join(test_dir.path, 'working')

        cucumber_html_report_path = os.path.join(work_dir_path, 'cucumber.html')
        cucumber_json_report_path = os.path.join(work_dir_path, 'cucumber.json')

        test_dir.write(pom_file_name, pom_content)

        pom_file_path = os.path.join(test_dir.path, pom_file_name)
        step_config = {
            'pom-file': pom_file_path,
            'selenium-hub-url': selenium_hub_url,
            'target-base-url': target_base_url
        }
        if fail_on_no_tests is not None:
            step_config['fail-on-no-tests'] = fail_on_no_tests
        if uat_maven_profile is not None:
            step_config['uat-maven-profile'] = uat_maven_profile
        else:
            uat_maven_profile = 'integration-test'
        step_implementer = self.create_step_implementer(
            step_config=step_config,
            results_dir_path=results_dir_path,
            results_file_name=results_file_name,
            work_dir_path=work_dir_path,
        )

        # mock generating settings
        settings_file_path = "/does/not/matter/settings.xml"
        def generate_maven_settings_side_effect():
            return settings_file_path
        generate_maven_settings_mock.side_effect = generate_maven_settings_side_effect

        # mock effective pom
        def write_effective_pom_mock_side_effect(pom_file_path, output_path):
            create_parent_dir(pom_file_path)
            copyfile(pom_file_path, output_path)
        write_effective_pom_mock.side_effect = write_effective_pom_mock_side_effect

        # mock test results
        if write_mock_test_results:
            mvn_mock.side_effect = MaveStepImplementerTestCase.create_mvn_side_effect(
                pom_file=pom_file_path,
                artifact_parent_dir=surefire_reports_dir,
                artifact_names=[
                    f'{group_id}.{artifact_id}.CucumberTest.txt',
                    f'TEST-{group_id}.{artifact_id}.CucumberTest.xml'
                ],
                raise_error_on_tests=raise_error_on_tests
            )

        result = step_implementer._run_step()
        if assert_mvn_called:
            mvn_mock.assert_called_once_with(
                'clean',
                'test',
                f'-P{uat_maven_profile}',
                f'-Dselenium.hub.url={selenium_hub_url}',
                f'-Dtarget.base.url={target_base_url}',
                f'-Dcucumber.plugin=' \
                    f'html:{cucumber_html_report_path},' \
                    f'json:{cucumber_json_report_path}',
                '-f', pom_file_path,
                '-s', settings_file_path,
                _out=Any(IOBase),
                _err=Any(IOBase)
            )

        expected_step_result = StepResult(
            step_name='uat',
            sub_step_name='MavenCucumberSelenium',
            sub_step_implementer_name='MavenCucumberSelenium'
        )
        expected_step_result.success = expected_result_success
        expected_step_result.message = expected_result_message

        if assert_report_artifact:
            mvn_test_output_file_path = os.path.join(
                work_dir_path,
                'uat',
                'mvn_test_output.txt'
            )
            expected_step_result.add_artifact(
                description=f"Standard out and standard error by 'mvn -P{uat_maven_profile} test'.",
                name='maven-output',
                value=mvn_test_output_file_path
            )
            expected_step_result.add_artifact(
                description=f"Surefire reports generated by 'mvn -P{uat_maven_profile} test'.",
                name='surefire-reports',
                value=surefire_reports_dir
            )
            expected_step_result.add_artifact(
                description=f"Cucumber (HTML) report generated by 'mvn -P{uat_maven_profile} test'.",
                name='cucumber-report-html',
                value=cucumber_html_report_path
            )
            expected_step_result.add_artifact(
                description=f"Cucumber (JSON) report generated by 'mvn -P{uat_maven_profile} test'.",
                name='cucumber-report-json',
                value=cucumber_json_report_path
            )

        self.assertEqual(expected_step_result.get_step_result(), result.get_step_result())

    @patch.object(MavenCucumberSelenium, '_generate_maven_settings')
    @patch('sh.mvn', create=True)
    @patch('tssc.step_implementers.shared.maven_generic.write_effective_pom')
    def test__run_step_success_defaults(
        self,
        write_effective_pom_mock,
        mvn_mock,
        generate_maven_settings_mock
    ):
        with TempDirectory() as test_dir:
            group_id = 'com.mycompany.app'
            artifact_id = 'my-app'
            version = '1.0'
            surefire_reports_dir = os.path.join(test_dir.path, 'target/surefire-reports')
            pom_content = bytes(
'''<project xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 http://maven.apache.org/xsd/maven-4.0.0.xsd"
xmlns="http://maven.apache.org/POM/4.0.0"
xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
    <modelVersion>4.0.0</modelVersion>
    <groupId>{group_id}</groupId>
    <artifactId>{artifact_id}</artifactId>
    <version>{version}</version>
    <properties>
        <maven.compiler.source>1.8</maven.compiler.source>
        <maven.compiler.target>1.8</maven.compiler.target>
    </properties>
    <build>
        <plugins>
            <plugin>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>${{surefire-plugin.version}}</version>
            </plugin>
        </plugins>
    </build>
</project>'''.format(
                    group_id=group_id,
                    artifact_id=artifact_id,
                    version=version
                ), 'utf-8'
            )

            self.__run__run_step_test(
                test_dir=test_dir,
                mvn_mock=mvn_mock,
                selenium_hub_url='https://test.xyz:4444',
                write_effective_pom_mock=write_effective_pom_mock,
                generate_maven_settings_mock=generate_maven_settings_mock,
                pom_content=pom_content,
                group_id=group_id,
                artifact_id=artifact_id,
                surefire_reports_dir=surefire_reports_dir
            )

    @patch.object(MavenCucumberSelenium, '_generate_maven_settings')
    @patch('sh.mvn', create=True)
    @patch('tssc.step_implementers.shared.maven_generic.write_effective_pom')
    def test__run_step_success_provided_profile_override(
        self,
        write_effective_pom_mock,
        mvn_mock,
        generate_maven_settings_mock
    ):
        with TempDirectory() as test_dir:
            group_id = 'com.mycompany.app'
            artifact_id = 'my-app'
            version = '1.0'
            surefire_reports_dir = os.path.join(test_dir.path, 'target/surefire-reports')
            pom_content = bytes(
'''<project xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 http://maven.apache.org/xsd/maven-4.0.0.xsd"
xmlns="http://maven.apache.org/POM/4.0.0"
xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
    <modelVersion>4.0.0</modelVersion>
    <groupId>{group_id}</groupId>
    <artifactId>{artifact_id}</artifactId>
    <version>{version}</version>
    <properties>
        <maven.compiler.source>1.8</maven.compiler.source>
        <maven.compiler.target>1.8</maven.compiler.target>
    </properties>
    <build>
        <plugins>
            <plugin>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>${{surefire-plugin.version}}</version>
            </plugin>
        </plugins>
    </build>
</project>'''.format(
                    group_id=group_id,
                    artifact_id=artifact_id,
                    version=version
                ), 'utf-8'
            )

            self.__run__run_step_test(
                test_dir=test_dir,
                mvn_mock=mvn_mock,
                selenium_hub_url='https://test.xyz:4444',
                write_effective_pom_mock=write_effective_pom_mock,
                generate_maven_settings_mock=generate_maven_settings_mock,
                pom_content=pom_content,
                group_id=group_id,
                artifact_id=artifact_id,
                surefire_reports_dir=surefire_reports_dir,
                uat_maven_profile='custom-uat-profile'
            )

    @patch.object(MavenCucumberSelenium, '_generate_maven_settings')
    @patch('sh.mvn', create=True)
    @patch('tssc.step_implementers.shared.maven_generic.write_effective_pom')
    def test__run_step_success_provided_pom_file_override(
        self,
        write_effective_pom_mock,
        mvn_mock,
        generate_maven_settings_mock
    ):
        with TempDirectory() as test_dir:
            group_id = 'com.mycompany.app'
            artifact_id = 'my-app'
            version = '1.0'
            surefire_reports_dir = os.path.join(test_dir.path, 'target/surefire-reports')
            pom_content = bytes(
'''<project xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 http://maven.apache.org/xsd/maven-4.0.0.xsd"
xmlns="http://maven.apache.org/POM/4.0.0"
xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
    <modelVersion>4.0.0</modelVersion>
    <groupId>{group_id}</groupId>
    <artifactId>{artifact_id}</artifactId>
    <version>{version}</version>
    <properties>
        <maven.compiler.source>1.8</maven.compiler.source>
        <maven.compiler.target>1.8</maven.compiler.target>
    </properties>
    <build>
        <plugins>
            <plugin>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>${{surefire-plugin.version}}</version>
            </plugin>
        </plugins>
    </build>
</project>'''.format(
                    group_id=group_id,
                    artifact_id=artifact_id,
                    version=version
                ), 'utf-8'
            )

            self.__run__run_step_test(
                test_dir=test_dir,
                mvn_mock=mvn_mock,
                selenium_hub_url='https://test.xyz:4444',
                write_effective_pom_mock=write_effective_pom_mock,
                generate_maven_settings_mock=generate_maven_settings_mock,
                pom_content=pom_content,
                group_id=group_id,
                artifact_id=artifact_id,
                surefire_reports_dir=surefire_reports_dir,
                pom_file_name='custom-pom.xml'
            )

    @patch.object(MavenCucumberSelenium, '_generate_maven_settings')
    @patch('sh.mvn', create=True)
    @patch('tssc.step_implementers.shared.maven_generic.write_effective_pom')
    def test__run_step_success_provided_fail_on_no_tests_false_with_tests(
        self,
        write_effective_pom_mock,
        mvn_mock,
        generate_maven_settings_mock
    ):
        with TempDirectory() as test_dir:
            group_id = 'com.mycompany.app'
            artifact_id = 'my-app'
            version = '1.0'
            surefire_reports_dir = os.path.join(test_dir.path, 'target/surefire-reports')
            pom_content = bytes(
'''<project xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 http://maven.apache.org/xsd/maven-4.0.0.xsd"
xmlns="http://maven.apache.org/POM/4.0.0"
xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
    <modelVersion>4.0.0</modelVersion>
    <groupId>{group_id}</groupId>
    <artifactId>{artifact_id}</artifactId>
    <version>{version}</version>
    <properties>
        <maven.compiler.source>1.8</maven.compiler.source>
        <maven.compiler.target>1.8</maven.compiler.target>
    </properties>
    <build>
        <plugins>
            <plugin>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>${{surefire-plugin.version}}</version>
            </plugin>
        </plugins>
    </build>
</project>'''.format(
                    group_id=group_id,
                    artifact_id=artifact_id,
                    version=version
                ), 'utf-8'
            )

            self.__run__run_step_test(
                test_dir=test_dir,
                mvn_mock=mvn_mock,
                selenium_hub_url='https://test.xyz:4444',
                write_effective_pom_mock=write_effective_pom_mock,
                generate_maven_settings_mock=generate_maven_settings_mock,
                pom_content=pom_content,
                group_id=group_id,
                artifact_id=artifact_id,
                surefire_reports_dir=surefire_reports_dir,
                fail_on_no_tests=False,
                write_mock_test_results=True,
                expected_result_success=True
            )

    @patch.object(MavenCucumberSelenium, '_generate_maven_settings')
    @patch('sh.mvn', create=True)
    @patch('tssc.step_implementers.shared.maven_generic.write_effective_pom')
    def test__run_step_success_provided_fail_on_no_tests_false_with_no_tests(
        self,
        write_effective_pom_mock,
        mvn_mock,
        generate_maven_settings_mock
    ):
        with TempDirectory() as test_dir:
            group_id = 'com.mycompany.app'
            artifact_id = 'my-app'
            version = '1.0'
            surefire_reports_dir = os.path.join(test_dir.path, 'target/surefire-reports')
            pom_content = bytes(
'''<project xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 http://maven.apache.org/xsd/maven-4.0.0.xsd"
xmlns="http://maven.apache.org/POM/4.0.0"
xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
    <modelVersion>4.0.0</modelVersion>
    <groupId>{group_id}</groupId>
    <artifactId>{artifact_id}</artifactId>
    <version>{version}</version>
    <properties>
        <maven.compiler.source>1.8</maven.compiler.source>
        <maven.compiler.target>1.8</maven.compiler.target>
    </properties>
    <build>
        <plugins>
            <plugin>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>${{surefire-plugin.version}}</version>
            </plugin>
        </plugins>
    </build>
</project>'''.format(
                    group_id=group_id,
                    artifact_id=artifact_id,
                    version=version
                ), 'utf-8'
            )

            self.__run__run_step_test(
                test_dir=test_dir,
                mvn_mock=mvn_mock,
                selenium_hub_url='https://test.xyz:4444',
                write_effective_pom_mock=write_effective_pom_mock,
                generate_maven_settings_mock=generate_maven_settings_mock,
                pom_content=pom_content,
                group_id=group_id,
                artifact_id=artifact_id,
                surefire_reports_dir=surefire_reports_dir,
                fail_on_no_tests=False,
                write_mock_test_results=False,
                expected_result_success=True,
                expected_result_message="No user acceptance tests defined" \
                    " using maven profile (integration-test)," \
                    " but 'fail-on-no-tests' is False."
            )

    @patch.object(MavenCucumberSelenium, '_generate_maven_settings')
    @patch('sh.mvn', create=True)
    @patch('tssc.step_implementers.shared.maven_generic.write_effective_pom')
    def test__run_step_fail_provided_fail_on_no_tests_true_with_no_tests(
        self,
        write_effective_pom_mock,
        mvn_mock,
        generate_maven_settings_mock
    ):
        with TempDirectory() as test_dir:
            group_id = 'com.mycompany.app'
            artifact_id = 'my-app'
            version = '1.0'
            surefire_reports_dir = os.path.join(test_dir.path, 'target/surefire-reports')
            pom_content = bytes(
'''<project xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 http://maven.apache.org/xsd/maven-4.0.0.xsd"
xmlns="http://maven.apache.org/POM/4.0.0"
xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
    <modelVersion>4.0.0</modelVersion>
    <groupId>{group_id}</groupId>
    <artifactId>{artifact_id}</artifactId>
    <version>{version}</version>
    <properties>
        <maven.compiler.source>1.8</maven.compiler.source>
        <maven.compiler.target>1.8</maven.compiler.target>
    </properties>
    <build>
        <plugins>
            <plugin>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>${{surefire-plugin.version}}</version>
            </plugin>
        </plugins>
    </build>
</project>'''.format(
                    group_id=group_id,
                    artifact_id=artifact_id,
                    version=version
                ), 'utf-8'
            )

            self.__run__run_step_test(
                test_dir=test_dir,
                mvn_mock=mvn_mock,
                selenium_hub_url='https://test.xyz:4444',
                write_effective_pom_mock=write_effective_pom_mock,
                generate_maven_settings_mock=generate_maven_settings_mock,
                pom_content=pom_content,
                group_id=group_id,
                artifact_id=artifact_id,
                surefire_reports_dir=surefire_reports_dir,
                fail_on_no_tests=True,
                write_mock_test_results=False,
                expected_result_success=False,
                expected_result_message="No user acceptance tests defined" \
                    " using maven profile (integration-test)."
            )

    @patch.object(MavenCucumberSelenium, '_generate_maven_settings')
    @patch('sh.mvn', create=True)
    @patch('tssc.step_implementers.shared.maven_generic.write_effective_pom')
    def test__run_step_fail_no_surefire_plugin(
        self,
        write_effective_pom_mock,
        mvn_mock,
        generate_maven_settings_mock
    ):
        with TempDirectory() as test_dir:
            group_id = 'com.mycompany.app'
            artifact_id = 'my-app'
            version = '1.0'
            surefire_reports_dir = os.path.join(test_dir.path, 'target/surefire-reports')
            pom_content = bytes(
'''<project xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 http://maven.apache.org/xsd/maven-4.0.0.xsd"
xmlns="http://maven.apache.org/POM/4.0.0"
xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
    <modelVersion>4.0.0</modelVersion>
    <groupId>{group_id}</groupId>
    <artifactId>{artifact_id}</artifactId>
    <version>{version}</version>
    <properties>
        <maven.compiler.source>1.8</maven.compiler.source>
        <maven.compiler.target>1.8</maven.compiler.target>
    </properties>
    <build>
        <plugins>
        </plugins>
    </build>
</project>'''.format(
                    group_id=group_id,
                    artifact_id=artifact_id,
                    version=version
                ), 'utf-8'
            )

            effective_pom_path = os.path.join(
                test_dir.path,
                'working',
                'effective-pom.xml'
            )
            self.__run__run_step_test(
                test_dir=test_dir,
                mvn_mock=mvn_mock,
                selenium_hub_url='https://test.xyz:4444',
                write_effective_pom_mock=write_effective_pom_mock,
                generate_maven_settings_mock=generate_maven_settings_mock,
                pom_content=pom_content,
                group_id=group_id,
                artifact_id=artifact_id,
                surefire_reports_dir=surefire_reports_dir,
                expected_result_success=False,
                expected_result_message='Unit test dependency "maven-surefire-plugin" ' \
                    f'missing from effective pom ({effective_pom_path}).',
                assert_mvn_called=False,
                assert_report_artifact=False
            )

    @patch.object(MavenCucumberSelenium, '_generate_maven_settings')
    @patch('sh.mvn', create=True)
    @patch('tssc.step_implementers.shared.maven_generic.write_effective_pom')
    def test__run_step_success_pom_specified_reports_dir(
        self,
        write_effective_pom_mock,
        mvn_mock,
        generate_maven_settings_mock
    ):
        with TempDirectory() as test_dir:
            group_id = 'com.mycompany.app'
            artifact_id = 'my-app'
            version = '1.0'
            surefire_reports_dir = os.path.join(test_dir.path, 'target/surefire-reports')
            pom_content = bytes(
'''<project xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 http://maven.apache.org/xsd/maven-4.0.0.xsd"
xmlns="http://maven.apache.org/POM/4.0.0"
xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
    <modelVersion>4.0.0</modelVersion>
    <groupId>{group_id}</groupId>
    <artifactId>{artifact_id}</artifactId>
    <version>{version}</version>
    <properties>
        <maven.compiler.source>1.8</maven.compiler.source>
        <maven.compiler.target>1.8</maven.compiler.target>
    </properties>
    <build>
        <plugins>
            <plugin>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>${{surefire-plugin.version}}</version>
                <configuration>
                    <reportsDirectory>{surefire_reports_dir}</reportsDirectory>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>'''.format(
                    group_id=group_id,
                    artifact_id=artifact_id,
                    version=version,
                    surefire_reports_dir=surefire_reports_dir
                ), 'utf-8'
            )

            self.__run__run_step_test(
                test_dir=test_dir,
                mvn_mock=mvn_mock,
                selenium_hub_url='https://test.xyz:4444',
                write_effective_pom_mock=write_effective_pom_mock,
                generate_maven_settings_mock=generate_maven_settings_mock,
                pom_content=pom_content,
                group_id=group_id,
                artifact_id=artifact_id,
                surefire_reports_dir=surefire_reports_dir
            )

    @patch.object(MavenCucumberSelenium, '_generate_maven_settings')
    @patch('sh.mvn', create=True)
    @patch('tssc.step_implementers.shared.maven_generic.write_effective_pom')
    def test__run_step_fail_mvn_test_failure(
        self,
        write_effective_pom_mock,
        mvn_mock,
        generate_maven_settings_mock
    ):
        with TempDirectory() as test_dir:
            group_id = 'com.mycompany.app'
            artifact_id = 'my-app'
            version = '1.0'
            surefire_reports_dir = os.path.join(test_dir.path, 'target/surefire-reports')
            pom_content = bytes(
'''<project xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 http://maven.apache.org/xsd/maven-4.0.0.xsd"
xmlns="http://maven.apache.org/POM/4.0.0"
xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
    <modelVersion>4.0.0</modelVersion>
    <groupId>{group_id}</groupId>
    <artifactId>{artifact_id}</artifactId>
    <version>{version}</version>
    <properties>
        <maven.compiler.source>1.8</maven.compiler.source>
        <maven.compiler.target>1.8</maven.compiler.target>
    </properties>
    <build>
        <plugins>
            <plugin>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>${{surefire-plugin.version}}</version>
            </plugin>
        </plugins>
    </build>
</project>'''.format(
                    group_id=group_id,
                    artifact_id=artifact_id,
                    version=version
                ), 'utf-8'
            )

            self.__run__run_step_test(
                test_dir=test_dir,
                mvn_mock=mvn_mock,
                selenium_hub_url='https://test.xyz:4444',
                write_effective_pom_mock=write_effective_pom_mock,
                generate_maven_settings_mock=generate_maven_settings_mock,
                pom_content=pom_content,
                group_id=group_id,
                artifact_id=artifact_id,
                surefire_reports_dir=surefire_reports_dir,
                raise_error_on_tests=True,
                expected_result_success=False,
                expected_result_message="User acceptance test failures. See 'maven-output'" \
                    ", 'surefire-reports', 'cucumber-report-html', and 'cucumber-report-json'" \
                    " report artifacts for details."
            )