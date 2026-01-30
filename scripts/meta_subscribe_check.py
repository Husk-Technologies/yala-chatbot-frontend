import os
import sys
import requests

from dotenv import load_dotenv, find_dotenv


load_dotenv(find_dotenv())


def main() -> int:
    api_version = os.getenv("META_API_VERSION", "v20.0")
    access_token = os.getenv("META_WA_ACCESS_TOKEN", "")
    waba_id = os.getenv("META_WA_WABA_ID", "")

    if not access_token or not waba_id:
        print("Missing META_WA_ACCESS_TOKEN or META_WA_WABA_ID")
        return 2

    base = f"https://graph.facebook.com/{api_version}"

    # 1) Check which apps are subscribed to this WABA
    url = f"{base}/{waba_id}/subscribed_apps"
    resp = requests.get(url, headers={"Authorization": f"Bearer {access_token}"}, timeout=15)
    print("GET subscribed_apps:", resp.status_code)
    print(resp.text)

    # 2) Optionally subscribe the current app (Meta infers the app from the token)
    if "--subscribe" in sys.argv:
        resp2 = requests.post(url, headers={"Authorization": f"Bearer {access_token}"}, timeout=15)
        print("POST subscribed_apps:", resp2.status_code)
        print(resp2.text)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
