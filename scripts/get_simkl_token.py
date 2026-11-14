#!/usr/bin/env python3
"""Helper script to authorize and obtain Simkl User Access Token via PIN flow.

Simkl supports a device PIN authorization flow:
1. Request a user PIN from https://api.simkl.com/oauth/pin?client_id=...
2. User opens the verification URL in browser and clicks 'Authorize'.
3. Script polls the check endpoint and retrieves the actual `access_token`.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


def load_env(env_path: Path) -> dict:
    env = {}
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip().strip("'\"")
    return env


def update_env_file(env_path: Path, updates: dict) -> None:
    lines = []
    keys_updated = set()
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

    new_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            k, _ = stripped.split("=", 1)
            k = k.strip()
            if k in updates:
                new_lines.append(f"{k}={updates[k]}\n")
                keys_updated.add(k)
                continue
        new_lines.append(line)

    for k, v in updates.items():
        if k not in keys_updated:
            new_lines.append(f"{k}={v}\n")

    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)


def main():
    project_root = Path(__file__).resolve().parent.parent
    env_path = project_root / ".env"
    env = load_env(env_path)

    client_id = env.get("SIMKL_CLIENT_ID") or os.environ.get("SIMKL_CLIENT_ID")
    if not client_id or client_id.startswith("your_"):
        print("❌ Błąd: SIMKL_CLIENT_ID nie jest ustawiony w pliku .env!")
        print("Wpisz swój Client ID z panelu Simkl do pliku .env i spróbuj ponownie.")
        sys.exit(1)

    print("==================================================")
    print("🔑 Simkl OAuth PIN Authorization Helper")
    print("==================================================")
    print("Pobieram kod autoryzacji PIN z Simkl API...")

    pin_init_url = f"https://api.simkl.com/oauth/pin?client_id={client_id}"
    req = urllib.request.Request(
        pin_init_url,
        headers={"Content-Type": "application/json", "simkl-api-key": client_id},
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"❌ Błąd połączenia z Simkl API: {e}")
        sys.exit(1)

    user_code = data.get("user_code")
    verification_url = data.get("verification_url", f"https://simkl.com/pin/{user_code}")
    expires_in = data.get("expires_in", 900)
    interval = data.get("interval", 5)

    print("\n👉 Otwórz poniższy link w swojej przeglądarce i kliknij 'Authorize':")
    print(f"   {verification_url}\n")
    print(f"(Kod PIN: {user_code}, wygasa za {expires_in // 60} minut)")
    print("Oczekuję na potwierdzenie w przeglądarce", end="", flush=True)

    check_url = f"https://api.simkl.com/oauth/pin/{user_code}?client_id={client_id}"
    start_time = time.time()

    while time.time() - start_time < expires_in:
        time.sleep(interval)
        print(".", end="", flush=True)

        check_req = urllib.request.Request(
            check_url,
            headers={"Content-Type": "application/json", "simkl-api-key": client_id},
        )
        try:
            with urllib.request.urlopen(check_req, timeout=15) as resp:
                check_data = json.loads(resp.read().decode("utf-8"))
                result = check_data.get("result")
                if result == "OK":
                    access_token = check_data.get("access_token")
                    print("\n\n🎉 Sukces! Otrzymano token autoryzacyjny użytkownika!")

                    # Pobierzmy też od razu dane profilu (username/id)
                    user_info_url = "https://api.simkl.com/users/settings"
                    user_req = urllib.request.Request(
                        user_info_url,
                        headers={
                            "simkl-api-key": client_id,
                            "Authorization": f"Bearer {access_token}",
                        },
                    )
                    username = None
                    try:
                        with urllib.request.urlopen(user_req, timeout=10) as u_resp:
                            u_data = json.loads(u_resp.read().decode("utf-8"))
                            user_obj = u_data.get("user", {})
                            username = user_obj.get("name") or str(user_obj.get("id"))
                            print(f"👤 Zalogowany jako użytkownik Simkl: {username}")
                    except Exception:
                        pass

                    # Zaktualizujmy plik .env
                    updates = {"SIMKL_USER_TOKEN": access_token}
                    if username:
                        updates["SIMKL_USERNAME"] = username

                    # Jeśli w SIMKL_USER_TOKEN był omyłkowo wklejony client_secret, przenieśmy go do SIMKL_CLIENT_SECRET
                    old_token = env.get("SIMKL_USER_TOKEN")
                    if old_token and old_token != access_token and not env.get("SIMKL_CLIENT_SECRET"):
                        updates["SIMKL_CLIENT_SECRET"] = old_token

                    update_env_file(env_path, updates)
                    print(f"✅ Zaktualizowano {env_path} (ustawiono SIMKL_USER_TOKEN i SIMKL_USERNAME).")
                    return
        except urllib.error.HTTPError as e:
            # 400/404 can mean authorization pending
            pass
        except Exception:
            pass

    print("\n⏰ Czas na autoryzację minął. Uruchom skrypt ponownie.")


if __name__ == "__main__":
    main()
