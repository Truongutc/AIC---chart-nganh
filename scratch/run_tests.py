import pytest
import sys

class SafeReporter:
    def __init__(self):
        self.passed_count = 0
        self.failed_count = 0
        self.skipped_count = 0
        self.failures = []

    def pytest_collectreport(self, report):
        if report.failed:
            print(f"COLLECTION FAIL: {report.nodeid}")
            print(report.longreprtext)

    def pytest_runtest_logreport(self, report):
        if report.when == 'call':
            if report.passed:
                self.passed_count += 1
                print(f"PASS: {report.nodeid}")
            elif report.failed:
                self.failed_count += 1
                self.failures.append((report.nodeid, report.longreprtext))
                print(f"FAIL: {report.nodeid}")
            elif report.skipped:
                self.skipped_count += 1
                print(f"SKIP: {report.nodeid}")

    def pytest_sessionfinish(self, session, exitstatus):
        print("\n" + "="*50)
        print("TEST RUN SUMMARY")
        print("="*50)
        print(f"Passed:  {self.passed_count}")
        print(f"Failed:  {self.failed_count}")
        print(f"Skipped: {self.skipped_count}")
        if self.failures:
            print("\n" + "="*50)
            print("DETAILED FAILURES")
            print("="*50)
            for nodeid, error in self.failures:
                print(f"\nFailure in {nodeid}:")
                print(error)
                print("-" * 40)

if __name__ == '__main__':
    reporter = SafeReporter()
    exit_code = pytest.main(['-p', 'no:terminal', 'tests'], plugins=[reporter])
    sys.exit(exit_code)
