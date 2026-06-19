from tinvest.config_manager import ConfigManager
import json

def test_parsing():
    cm = ConfigManager("test_config.json")
    
    # Test 1: Raw Headers
    headers = """
Cookie: language=vi-VN; ASP.NET_SessionId=test_session_id; vst_usr_lg_token=test_token
__RequestVerificationToken: ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789abcdefghijklmnopqrstuvwxyz0123456789_Token_Value_Longer_Than_50
"""
    print("Testing Raw Headers...")
    success = cm.parse_input(headers)
    assert success
    assert cm.get("cookies")["ASP.NET_SessionId"] == "test_session_id"
    assert cm.get("payload_token").startswith("ABCDEFGHIJKLMNOP")
    print("Raw Headers OK")

    # Test 2: cURL
    curl = """
curl 'https://finance.vietstock.vn/data/KQGDThongKeGiaPaging' \\
  -H 'Cookie: language=vi-VN; ASP.NET_SessionId=curl_session_id' \\
  --data-raw 'page=1&pageSize=20&__RequestVerificationToken=CURL_TOKEN_VALUE_ABC_123_XYZ_LONG_STRING_HERE'
"""
    print("\nTesting cURL...")
    success = cm.parse_input(curl)
    assert success
    assert cm.get("cookies")["ASP.NET_SessionId"] == "curl_session_id"
    assert cm.get("payload_token") == "CURL_TOKEN_VALUE_ABC_123_XYZ_LONG_STRING_HERE"
    print("cURL OK")

    # Test 3: URL with params
    url = "https://finance.vietstock.vn/data/KQGDThongKeGiaPaging?catID=1&__RequestVerificationToken=URL_TOKEN_VALUE_VERY_LONG_STRING_REPEATED_TO_MATCH_THE_EIGHTY_CHARACTER_THRESHOLD_XYZ_123_456_789"
    print("\nTesting URL...")
    success = cm.parse_input(url)
    assert success
    assert cm.get("payload_token") == "URL_TOKEN_VALUE_VERY_LONG_STRING_REPEATED_TO_MATCH_THE_EIGHTY_CHARACTER_THRESHOLD_XYZ_123_456_789"
    print("URL OK")

    # Test 4: Just the token hash
    just_token = "JUST_A_VERY_LONG_TOKEN_HASH_VALUE_THAT_IS_MORE_THAN_120_CHARACTERS_LONG_BECAUSE_VIETSTOCK_TOKENS_ARE_QUITE_LONG_USUALLY"
    print("\nTesting Just Token Hash...")
    success = cm.parse_input(just_token)
    assert success
    assert cm.get("payload_token") == just_token
    print("Just Token Hash OK")

    print("\nAll tests passed!")

if __name__ == "__main__":
    test_parsing()
