import pytest

from app.sources.detect import Detected, detect


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        (
            "https://broadcom.wd1.myworkdayjobs.com/External_Career",
            Detected(
                "workday",
                {
                    "host": "broadcom.wd1.myworkdayjobs.com",
                    "tenant": "broadcom",
                    "site": "External_Career",
                },
                "broadcom",
            ),
        ),
        (
            "https://accenture.wd103.myworkdayjobs.com/en-US/AccentureCareers/job/Bengaluru/X_R1",
            Detected(
                "workday",
                {
                    "host": "accenture.wd103.myworkdayjobs.com",
                    "tenant": "accenture",
                    "site": "AccentureCareers",
                },
                "accenture",
            ),
        ),
        (
            "https://egug.fa.us2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1/jobs",
            Detected("oracle_hcm", {"host": "egug.fa.us2.oraclecloud.com", "site": "CX_1"}, "egug"),
        ),
        (
            "https://paypal.eightfold.ai/careers?query=intern",
            Detected(
                "eightfold", {"host": "paypal.eightfold.ai", "domain": "paypal.com"}, "paypal"
            ),
        ),
        (
            "https://apply.careers.microsoft.com/careers?pid=1970393556642428",
            Detected(
                "eightfold",
                {"host": "apply.careers.microsoft.com", "domain": "microsoft.com"},
                "microsoft",
            ),
        ),
        (
            "https://careers.qualcomm.com/careers/job/446700000001",
            Detected(
                "eightfold", {"host": "careers.qualcomm.com", "domain": "qualcomm.com"}, "qualcomm"
            ),
        ),
        (
            "https://jobs.lever.co/paytm",
            Detected("lever", {"site": "paytm"}, "paytm"),
        ),
        (
            "https://jobs.lever.co/paytm/9eed4fec-73f7-4114-a5d3-b2f689c92e8c",
            Detected("lever", {"site": "paytm"}, "paytm"),
        ),
        (
            "https://api.lever.co/v0/postings/meesho?mode=json",
            Detected("lever", {"site": "meesho"}, "meesho"),
        ),
        ("https://jobs.lever.co/", None),
        ("https://jobs.eu.lever.co/acme", None),  # EU boards use another API host
        (
            "https://job-boards.eu.greenhouse.io/groww/jobs/4970739101",
            Detected("greenhouse", {"board": "groww"}, "groww"),
        ),
        (
            "https://boards.greenhouse.io/embed/job_board?for=inmobi",
            Detected("greenhouse", {"board": "inmobi"}, "inmobi"),
        ),
        (
            "https://boards-api.greenhouse.io/v1/boards/razorpaysoftwareprivatelimited/jobs",
            Detected(
                "greenhouse",
                {"board": "razorpaysoftwareprivatelimited"},
                "razorpaysoftwareprivatelimited",
            ),
        ),
        ("https://boards.greenhouse.io/", None),
        ("https://example.com/jobs", None),
        ("https://careers.example.com/careers", None),  # /careers alone is not Eightfold
        ("not a url", None),
        ("ftp://broadcom.wd1.myworkdayjobs.com/External_Career", None),
    ],
)
def test_detect(url, expected):
    assert detect(url) == expected
