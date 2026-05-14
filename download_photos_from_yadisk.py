import requests
from pathlib import Path

PUBLIC_KEY = "https://disk.yandex.ru/d/9SbBwxqQuns8cw"
API = "https://cloud-api.yandex.net/v1/disk/public/resources"
DL = "https://cloud-api.yandex.net/v1/disk/public/resources/download"

ROOT = Path("photos")


def list_items(path: str):
    r = requests.get(API, params={"public_key": PUBLIC_KEY, "path": path, "limit": 1000}, timeout=30)
    r.raise_for_status()
    return r.json().get("_embedded", {}).get("items", [])


def download_file(remote_path: str, local_path: Path):
    r = requests.get(DL, params={"public_key": PUBLIC_KEY, "path": remote_path}, timeout=30)
    r.raise_for_status()
    href = r.json().get("href")
    if not href:
        raise RuntimeError(f"No href for {remote_path}")
    f = requests.get(href, timeout=60)
    f.raise_for_status()
    local_path.parent.mkdir(parents=True, exist_ok=True)
    local_path.write_bytes(f.content)


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    cat_dirs = [i for i in list_items("/2_фото") if i.get("type") == "dir"]
    total = 0
    for cat in cat_dirs:
        cat_name = cat["name"]
        sub = [i for i in list_items(f"/2_фото/{cat_name}/главные") if i.get("type") == "file"]
        for f in sub:
            name = f["name"]
            remote_path = f["path"]
            local_path = ROOT / cat_name / name
            download_file(remote_path, local_path)
            total += 1
            print(f"downloaded: {local_path}")
    print("total_downloaded", total)


if __name__ == "__main__":
    main()
