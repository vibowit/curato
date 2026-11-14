#!/usr/bin/env python3
"""Helper script to authorize and obtain Simkl User Access Token via modern Auth V2 Device Flow.

Simkl Auth V2 uses standard OAuth 2.0 Device Authorization Grant (RFC 8628):
1. POST https://api.simkl.com/oauth2/device with client_id.
2. User opens verification_uri (https://simkl.com/pin) and enters user_code.
3. Script polls POST https://api.simkl.com/oauth2/token with client_id and client_secret until user approves.
4. Updates .env with SIMKL_USER_TOKEN and detects SIMKL_USERNAME.
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
    client_secret = env.get("SIMKL_CLIENT_SECRET") or env.get("SIMKL_USER_TOKEN") or os.environ.get("SIMKL_CLIENT_SECRET")

    if not client_id or client_id.startswith("your_"):
        print("❌ Błąd: SIMKL_CLIENT_ID nie jest ustawiony w pliku .env!")
        print("Wpisz swój Client ID z panelu Simkl do pliku .env i spróbuj ponownie.")
        sys.exit(1)

    print("==================================================")
    print("🔑 Simkl OAuth 2.0 (Auth V2) Device Authorization")
    print("==================================================")
    print("Pobieram kod urządzenia z Simkl API (POST /oauth2/device)...")

    device_url = "https://api.simkl.com/oauth2/device"
    form_params = {"client_id": client_id}
    form_data = urllib.parse.urlencode(form_params).encode("utf-8")
    req = urllib.request.Request(
        device_url,
        data=form_data,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "simkl-api-key": client_id,
            "User-Agent": "PersonalMovieRecommender/0.1.0",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8")
        print(f"❌ Błąd połączenia z Simkl API: HTTP {e.code} - {err_body}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Błąd połączenia z Simkl API: {e}")
        sys.exit(1)

    device_code = data.get("device_code")
    user_code = data.get("user_code")
    verification_uri = data.get("verification_uri", "https://simkl.com/pin")
    verification_url = data.get("verification_url", f"{verification_uri}?code={user_code}")
    expires_in = data.get("expires_in", 900)
    interval = max(data.get("interval", 5), 5)

    print("\n👉 Otwórz poniższy link w swojej przeglądarce i zatwierdź aplikację:")
    print(f"   {verification_url}")
    print(f"\n(Kod PIN / user code: {user_code})")
    print(f"Kod wygasa za {expires_in // 60} minut.")
    print("\nOczekuję na potwierdzenie w przeglądarce", end="", flush=True)

    token_url = "https://api.simkl.com/oauth2/token"
    start_time = time.time()

    while time.time() - start_time < expires_in:
        time.sleep(interval)
        print(".", end="", flush=True)

        token_params = {
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            "client_id": client_id,
            "device_code": device_code,
        }
        if client_secret:
            token_params["client_secret"] = client_secret

        token_data = urllib.parse.urlencode(token_params).encode("utf-8")
        token_req = urllib.request.Request(
            token_url,
            data=token_data,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "simkl-api-key": client_id,
                "User-Agent": "PersonalMovieRecommender/0.1.0",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(token_req, timeout=15) as resp:
                token_resp = json.loads(resp.read().decode("utf-8"))
                access_token = token_resp.get("access_token")
                if access_token:
                    print("\n\n🎉 Sukces! Otrzymano token autoryzacyjny użytkownika!")

                    # Pobierzmy dane zalogowanego użytkownika (settings / username)
                    username = None
                    try:
                        user_info_url = "https://api.simkl.com/users/settings"
                        user_req = urllib.request.Request(
                            user_info_url,
                            headers={
                                "simkl-api-key": client_id,
                                "Authorization": f"Bearer {access_token}",
                                "User-Agent": "PersonalMovieRecommender/0.1.0",
                            },
                        )
                        with urllib.request.urlopen(user_req, timeout=10) as u_resp:
                            u_data = json.loads(u_resp.read().decode("utf-8"))
                            user_obj = u_data.get("user", {})
                            username = user_obj.get("name") or str(user_obj.get("id"))
                            print(f"👤 Zalogowany użytkownik Simkl: {username}")
                    except Exception as ue:
                        print(f"[Ostrzeżenie] Nie udało się automatycznie pobrać nazwy użytkownika ({ue})")

                    # Aktualizujemy .env
                    updates = {
                        "SIMKL_USER_TOKEN": access_token,
                        "SIMKL_CLIENT_SECRET": client_secret or "",
                    }
                    if username:
                        updates["SIMKL_USERNAME"] = username

                    update_env_file(env_path, updates)
                    print(f"✅ Zaktualizowano {env_path} (ustawiono SIMKL_USER_TOKEN i SIMKL_USERNAME).")
                    return
        except urllib.error.HTTPError as e:
            try:
                err_data = json.loads(e.read().decode("utf-8"))
                error_type = err_data.get("error")
                if error_type in ("authorization_pending", "slow_down"):
                    continue
                else:
                    print(f"\n❌ Błąd autoryzacji: {err_data}")
                    sys.exit(1)
            except Exception:
                continue
        except Exception:
            continue

    print("\n⏰ Czas na autoryzację minął. Uruchom skrypt ponownie.")


if __name__ == "__main__":
    main()
