"""Build platform search URLs that match the job title shown on each card."""

import re
from urllib.parse import quote_plus


def _slug(text: str) -> str:
    s = re.sub(r"[^\w\s-]", "", text.lower())
    s = re.sub(r"[\s_]+", "-", s.strip())
    return re.sub(r"-+", "-", s).strip("-")[:80]


def _normalize_location(location: str) -> tuple[str, str]:
    """Return (display location, platform slug/query value)."""
    loc = (location or "India").strip()
    low = loc.lower()
    if low in ("remote", "work from home", "wfh", "anywhere"):
        return "Remote", "remote"
    mapping = {
        "bengaluru": "bangalore",
        "bangalore": "bangalore",
        "mumbai": "mumbai",
        "delhi": "delhi",
        "new delhi": "delhi",
        "hyderabad": "hyderabad",
        "pune": "pune",
        "chennai": "chennai",
        "kolkata": "kolkata",
        "gurgaon": "gurgaon",
        "gurugram": "gurgaon",
        "noida": "noida",
        "india": "india",
    }
    for key, slug in mapping.items():
        if key in low:
            return loc, slug
    return loc, _slug(loc) or "india"


def build_platform_search_url(
    platform: str,
    title: str,
    location: str = "",
    company: str = "",
    skills: list[str] | None = None,
) -> str:
    """
    Return a search URL where results match the card title on that platform.
    Uses job title only (skills are shown on card but not mixed into the query).
    """
    _ = company, skills  # kept for API compatibility
    plat = (platform or "LinkedIn").lower()
    title_q = " ".join(title.split()).strip() or "jobs"
    title_enc = quote_plus(title_q)
    display_loc, loc_slug = _normalize_location(location)
    loc_enc = quote_plus(display_loc)
    title_slug = _slug(title_q)

    if "linkedin" in plat:
        return (
            f"https://www.linkedin.com/jobs/search/"
            f"?keywords={title_enc}&location={loc_enc}"
        )

    if "naukri" in plat:
        if loc_slug == "remote":
            return (
                f"https://www.naukri.com/{title_slug}-jobs"
                f"?k={title_enc}&workType=remote"
            )
        return (
            f"https://www.naukri.com/{title_slug}-jobs-in-{loc_slug}"
            f"?k={title_enc}&l={quote_plus(loc_slug)}"
        )

    if "indeed" in plat:
        return f"https://in.indeed.com/jobs?q={title_enc}&l={loc_enc}"

    if "internshala" in plat:
        kw_slug = title_slug[:60]
        if "intern" in title_q.lower() or "intern" in plat:
            return f"https://internshala.com/internships/keywords-{kw_slug}/"
        return f"https://internshala.com/jobs/keywords-{kw_slug}/"

    return f"https://www.google.com/search?q={quote_plus(title_q + ' jobs ' + display_loc)}"
