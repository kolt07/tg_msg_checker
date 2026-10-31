from tg_msg_checker.analyzers.phones import PhoneAnalyzer


def test_ukrainian_phone_is_normalized():
    found = PhoneAnalyzer("UA").analyze("дзвоніть 050 123 45 67 сьогодні")
    assert len(found) == 1
    assert found[0].name == "phone"
    assert found[0].text == "050 123 45 67"
    assert found[0].payload["normalized"] == "+380501234567"


def test_international_phone_and_noise():
    found = PhoneAnalyzer("UA").analyze("код 12345 і номер +380671112233")
    assert [item.payload["normalized"] for item in found] == ["+380671112233"]


def test_invalid_phone_is_ignored():
    assert PhoneAnalyzer("UA").analyze("номер 12345") == []
