import typer
import rich
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import re
from datetime import datetime
import time

app = typer.Typer()


def internet_connection():
    try:
        response = requests.get("https://www.google.com", timeout=5)
        return True
    except requests.ConnectionError:
        return False


def extract_urls_from_onclick(onclick_content):
    # More flexible patterns
    patterns = [
        # window.open patterns
        r"window\.open\s*\(\s*[\"'`]([^\"'`]+)[\"'`]",
        # window.location patterns
        r"window\.location(?:\.href)?\s*=\s*[\"'`]([^\"'`]+)[\"'`]",
        # location.href patterns
        r"location\.href\s*=\s*[\"'`]([^\"'`]+)[\"'`]",
        # direct javascript: URLs
        r"javascript:window\.open\([\"'`]([^\"'`]+)[\"'`]",
    ]

    urls = []
    for pattern in patterns:
        matches = re.findall(pattern, onclick_content, re.IGNORECASE)
        urls.extend(matches)

    return urls


def get_internal_links(url, base_domain):
    try:
        response = requests.get(
            url, timeout=5, stream=True
        )  # Stream to avoid large downloads
        response.raise_for_status()

        # Check if the content type is HTML
        content_type = response.headers.get("Content-Type", "")
        if "text/html" not in content_type:
            rich.print(
                f"[bold blue]Skipping[/bold blue] non-HTML content at {url} (Content-Type: {content_type})"
            )
            return {}

        response.encoding = response.apparent_encoding  # Ensure correct decoding
    except requests.RequestException as e:
        print(f"Failed to access {url}: {e}")
        return {}
    # soup = BeautifulSoup(response.text, "html.parser")
    try:
        soup = BeautifulSoup(response.content, "lxml")
    except Exception as e:
        print(f"Error parsing HTML from {url}: {e}")
        return {}

    # links = set()
    links = {}

    for a_tag in soup.find_all("a", href=True):
        link = urljoin(url, a_tag["href"])
        parsed_link = urlparse(link)
        if parsed_link.netloc.endswith(base_domain):
            # links.add(link)
            links[link] = url

    # Check for onclick attributes
    for element in soup.find_all(onclick=True):
        onclick_content = element["onclick"]
        matches = extract_urls_from_onclick(onclick_content)
        for match in matches:
            if match.startswith("http"):
                link = match  # Full URL
            else:
                link = urljoin(url, match)  # Relative path

            parsed_link = urlparse(link)
            if parsed_link.netloc.endswith(base_domain):
                # links.add(link)
                links[link] = url

    return links


def generate_report(base_url, results, elapsed_time):
    timestamp = datetime.now().strftime("%y%m%d_%H%M%S")
    filename_url = (
        base_url.replace("https://www.", "")
        .replace("http://www.", "")
        .replace(".", "_")
    )
    report_filename = f"linkcheck-{filename_url}-{timestamp}.md"
    total_links = len(results)

    sorted_results = sorted(results.items(), key=lambda x: (x[1][0] != 200, x[1][0]))
    non_ok_links = [
        (url, status, parent)
        for url, (status, parent) in sorted_results
        if status != 200
    ]

    rich.print(
        f"Generated report for [bold green]{filename_url}[/bold green] in {elapsed_time:.2f} seconds."
    )

    with open(report_filename, "w", encoding="utf-8") as report:
        report.write(f"# Link Analyse für {filename_url.replace("_", ".")}\n\n")
        report.write(f"**Anzahl analysierter Links:** `{total_links}`\n\n")
        report.write(f"**Dauer der Analyse:** `{elapsed_time:.2f} Sekunden`\n\n")

        report.write(f"\n## Nicht funktionierende Links\n\n")
        if not non_ok_links:
            report.write("Alle Links haben mit 200 OK geantwortet. 🎉\n\n")
        else:
            for url, status, parent in non_ok_links:
                display_url = url.replace("https://www.", "").replace("http://www.", "")
                display_parent = (
                    parent.replace("https://www.", "").replace("http://www.", "")
                    if parent
                    else "N/A"
                )
                report.write(
                    f"- Status: {status} – **[{display_url}](https://{display_url})** (Link befindet sich auf: `{display_parent}`)\n"
                )

        report.write(f"## Funktionierende Links\n\n")
        ok_links = [
            (url, status) for url, (status, _) in sorted_results if status == 200
        ]
        for url, status in ok_links:
            display_url = url.replace("https://www.", "").replace("http://www.", "")
            report.write(
                f"- Status: {status} – **[{display_url}](https://{display_url})**\n"
            )

    print(f"\n📄 Report saved as {report_filename}")


def check_links(base_url):
    start_time = time.time()
    base_domain = urlparse(base_url).netloc
    visited = set()
    # to_visit = {base_url}
    to_visit = {base_url: None}
    results = {}

    while to_visit:
        # url = to_visit.pop()
        url, parent = to_visit.popitem()
        if url in visited:
            continue

        visited.add(url)
        status_code = ""
        try:
            response = requests.get(url, timeout=(8, 8))
            status_code = response.status_code
            rich.print(f"Checking: {url} (found on: {parent})")
            if str(response.status_code).startswith("4"):
                rich.print(
                    f"  Status: [bold red]{response.status_code}[/bold red] {response.reason}"
                )
            elif str(response.status_code).startswith("5"):
                rich.print(
                    f"  Status: [bold purple]{response.status_code}[/bold purple] {response.reason}"
                )
            elif response.status_code == 200:
                rich.print(
                    f"  Status: [bold green]{response.status_code}[/bold green] {response.reason}"
                )
            else:
                rich.print(
                    f"  Status: [bold]{response.status_code}[/bold] {response.reason}"
                )
        except requests.RequestException as e:
            print(f"  Error: {e}")

        # results[url] = status_code
        results[url] = (status_code, parent)
        new_links = get_internal_links(url, base_domain)
        # to_visit.update(new_links - visited)
        for new_url, parent_url in new_links.items():
            if new_url not in visited:
                to_visit[new_url] = parent_url

    # Generate Markdown report
    elapsed_time = time.time() - start_time
    generate_report(base_url, results, elapsed_time)


@app.command()
def main(url_path: str = typer.Argument(..., help="URL die untersucht werden soll")):
    """CLI tool for reading and parsing an XML file."""
    if url_path.startswith("http"):
        check_links(url_path)
    else:
        check_links("https://www." + url_path)


if __name__ == "__main__":
    app(prog_name="linkonaut")
