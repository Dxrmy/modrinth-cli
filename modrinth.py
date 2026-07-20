import argparse
import sys
import json
import urllib.request
import urllib.parse
from urllib.error import URLError, HTTPError

BASE_URL = "https://api.modrinth.com/v2"

def _request(endpoint, params=None):
    url = f"{BASE_URL}{endpoint}"
    if params:
        query_string = urllib.parse.urlencode(params, doseq=True)
        url = f"{url}?{query_string}"
    
    req = urllib.request.Request(url, headers={'User-Agent': 'modrinth-cli (github.com/Dxrmy/modrinth-cli)'})
    try:
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode())
    except HTTPError as e:
        print(f"HTTP Error {e.code}: {e.read().decode()}")
        sys.exit(1)
    except URLError as e:
        print(f"URL Error: {e.reason}")
        sys.exit(1)

def display_filters(filter_type):
    if filter_type == 'categories':
        data = _request('/tag/category')
        print("Available Categories:")
        for item in data:
            print(f" - {item['name']} ({item['project_type']})")
    elif filter_type == 'loaders':
        data = _request('/tag/loader')
        print("Available Loaders:")
        for item in data:
            print(f" - {item['name']}")
    elif filter_type == 'versions':
        data = _request('/tag/game_version')
        print("Available Game Versions:")
        for item in data:
            print(f" - {item['version']}")
    else:
        print("Unknown filter type. Choose from: categories, loaders, versions")

def search_projects(query, project_type, game_versions, loaders, categories):
    facets = []
    
    if project_type:
        facets.append([f'project_type:{project_type}'])
    if game_versions:
        facets.append([f'versions:{v}' for v in game_versions])
    if loaders:
        facets.append([f'categories:{l}' for l in loaders])
    if categories:
        facets.append([f'categories:{c}' for c in categories])
        
    params = {
        'query': query,
        'limit': 10
    }
    if facets:
        params['facets'] = json.dumps(facets)
        
    data = _request('/search', params)
    
    print(f"Found {data['total_hits']} results. Showing top {len(data['hits'])}:")
    print("-" * 60)
    for hit in data['hits']:
        print(f"[{hit['project_type'].upper()}] {hit['title']} ({hit['slug']})")
        print(f"Description: {hit['description']}")
        print(f"Author: {hit['author']}")
        print(f"Downloads: {hit['downloads']}")
        print("-" * 60)

def download_project(slug, version=None, loader=None):
    print(f"Fetching versions for {slug}...")
    params = {}
    if loader:
        params['loaders'] = json.dumps([loader])
    if version:
        params['game_versions'] = json.dumps([version])
        
    versions = _request(f'/project/{slug}/version', params)
    
    if not versions:
        print("No versions found matching the criteria.")
        return
        
    latest_version = versions[0]
    file = latest_version['files'][0]
    download_url = file['url']
    filename = file['filename']
    
    print(f"Downloading {filename}...")
    
    try:
        urllib.request.urlretrieve(download_url, filename)
        print(f"Successfully downloaded {filename}")
    except Exception as e:
        print(f"Failed to download: {e}")

def main():
    parser = argparse.ArgumentParser(description="Modrinth CLI - Interact with the Modrinth API")
    
    subparsers = parser.add_subparsers(dest="command", help="Commands")
    
    # Search command
    search_parser = subparsers.add_parser("search", help="Search for projects")
    search_parser.add_argument("query", nargs="?", default="", help="Search query")
    search_parser.add_argument("-t", "--type", choices=["mod", "modpack", "resourcepack", "shader"], help="Filter by project type")
    search_parser.add_argument("-v", "--version", action="append", help="Filter by game version (can be used multiple times)")
    search_parser.add_argument("-l", "--loader", action="append", help="Filter by loader (e.g., fabric, forge)")
    search_parser.add_argument("-c", "--category", action="append", help="Filter by category")
    
    # Download command
    download_parser = subparsers.add_parser("download", help="Download a project")
    download_parser.add_argument("slug", help="Project slug or ID")
    download_parser.add_argument("-v", "--version", help="Specific game version to download for")
    download_parser.add_argument("-l", "--loader", help="Specific loader to download for")
    
    # Filters command
    filters_parser = subparsers.add_parser("filters", help="List available filters")
    filters_parser.add_argument("type", choices=["categories", "loaders", "versions"], help="Type of filters to list")
    
    args = parser.parse_args()
    
    if args.command == "search":
        search_projects(args.query, args.type, args.version, args.loader, args.category)
    elif args.command == "download":
        download_project(args.slug, args.version, args.loader)
    elif args.command == "filters":
        display_filters(args.type)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
