"""XML job feed for platform syndication (Indeed, Dice bots, ZipRecruiter)."""

import html
import xml.etree.ElementTree as ET
from xml.dom import minidom

from sqlalchemy.orm import Session

from database import JobPosting, PlatformPost
from jd_service import jd_to_text


def _employment_type(jd: dict) -> str:
    raw = (jd.get("employment_type") or "Full-time").lower()
    if "part" in raw:
        return "parttime"
    if "contract" in raw:
        return "contract"
    if "temp" in raw:
        return "temporary"
    return "fulltime"


def build_job_xml(
    posting: JobPosting,
    platform_post: PlatformPost,
    apply_url: str,
    recruiter_email: str = "",
) -> str:
    jd = posting.get_jd()
    description = jd_to_text(jd)
    company = jd.get("company") or "Company"
    location = jd.get("location") or "Remote"
    salary = (jd.get("salary_range") or "").strip()

    job = ET.Element("job")
    ET.SubElement(job, "title").text = posting.title
    ET.SubElement(job, "referencenumber").text = str(platform_post.id)
    ET.SubElement(job, "url").text = apply_url
    ET.SubElement(job, "company").text = company
    ET.SubElement(job, "city").text = location.split(",")[0].strip() if location else "Remote"
    ET.SubElement(job, "state").text = (
        location.split(",")[1].strip() if "," in location else ""
    )
    ET.SubElement(job, "country").text = "US"
    ET.SubElement(job, "description").text = description
    ET.SubElement(job, "date").text = platform_post.posted_at.strftime("%Y-%m-%d")
    ET.SubElement(job, "jobtype").text = _employment_type(jd)
    if salary:
        ET.SubElement(job, "salary").text = salary
    contact_email = recruiter_email or ""
    if contact_email:
        ET.SubElement(job, "email").text = contact_email

    root = ET.Element("source")
    ET.SubElement(root, "publisher").text = "AI Recruitment Portal"
    ET.SubElement(root, "lastBuildDate").text = platform_post.posted_at.isoformat()
    root.append(job)

    rough = ET.tostring(root, encoding="unicode")
    return minidom.parseString(rough).toprettyxml(indent="  ")


def build_multi_job_feed(
    db: Session,
    posts: list[PlatformPost],
    base_url: str,
) -> str:
    root = ET.Element("source")
    ET.SubElement(root, "publisher").text = "AI Recruitment Portal"

    for pp in posts:
        posting = pp.job_posting
        jd = posting.get_jd()
        apply_url = f"{base_url}/apply/{pp.apply_token}"
        description = jd_to_text(jd)
        company = jd.get("company") or "Company"
        location = jd.get("location") or "Remote"

        job = ET.Element("job")
        ET.SubElement(job, "title").text = posting.title
        ET.SubElement(job, "referencenumber").text = str(pp.id)
        ET.SubElement(job, "url").text = apply_url
        ET.SubElement(job, "company").text = company
        ET.SubElement(job, "city").text = location.split(",")[0].strip() if location else "Remote"
        ET.SubElement(job, "description").text = description
        ET.SubElement(job, "date").text = pp.posted_at.strftime("%Y-%m-%d")
        ET.SubElement(job, "jobtype").text = _employment_type(jd)
        root.append(job)

    rough = ET.tostring(root, encoding="unicode")
    return minidom.parseString(rough).toprettyxml(indent="  ")


def html_job_description(jd: dict) -> str:
    parts = [f"<p>{html.escape(jd.get('summary', ''))}</p>"]
    if jd.get("responsibilities"):
        parts.append("<h3>Responsibilities</h3><ul>")
        for item in jd["responsibilities"]:
            parts.append(f"<li>{html.escape(str(item))}</li>")
        parts.append("</ul>")
    if jd.get("required_skills"):
        parts.append("<h3>Required Skills</h3><ul>")
        for item in jd["required_skills"]:
            parts.append(f"<li>{html.escape(str(item))}</li>")
        parts.append("</ul>")
    if jd.get("qualifications"):
        parts.append("<h3>Qualifications</h3><ul>")
        for item in jd["qualifications"]:
            parts.append(f"<li>{html.escape(str(item))}</li>")
        parts.append("</ul>")
    return "\n".join(parts)
