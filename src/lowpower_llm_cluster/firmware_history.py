from __future__ import annotations

from typing import Any
from urllib.parse import urljoin

REVISION_KEYS=("revision","board_revision","pcb_revision","hardware_revision","rev")
VERSION_KEYS=("version","bios","bios_version","name")
DATE_KEYS=("date","release_date","released","publishdate","publish_date")
URL_KEYS=("url","download","download_url","file","file_url")


def _lower(row: dict[str,Any]) -> dict[str,Any]:
    return {str(k).casefold():v for k,v in row.items()}


def _pick(lower: dict[str,Any], keys: tuple[str,...]) -> Any:
    return next((lower[key] for key in keys if key in lower and lower[key] not in (None,"")),None)


def _revisions(value: Any) -> list[str]:
    if value in (None,""): return []
    if isinstance(value,list): values=value
    else: values=str(value).replace("/",",").replace(";",",").split(",")
    return list(dict.fromkeys(str(v).strip().upper().removeprefix("REV.").removeprefix("REV ").strip() for v in values if str(v).strip()))


def normalize_revision_scoped_bios_history(payload: Any, *, source_url: str) -> list[dict[str,Any]]:
    """Extract BIOS rows with explicit board-revision scope from manufacturer payloads."""
    rows=[]
    def walk(value: Any, inherited_revisions: list[str] | None=None) -> None:
        inherited_revisions=inherited_revisions or []
        if isinstance(value,list):
            for child in value: walk(child,inherited_revisions)
        elif isinstance(value,dict):
            lower=_lower(value)
            own=_revisions(_pick(lower,REVISION_KEYS)); revisions=own or inherited_revisions
            version=_pick(lower,VERSION_KEYS); date=_pick(lower,DATE_KEYS); file_url=_pick(lower,URL_KEYS)
            if version is not None and revisions and (date is not None or file_url is not None):
                rows.append({"version":str(version).strip(),"release_date":str(date).strip() if date is not None else None,"download_url":urljoin(source_url,str(file_url)) if file_url else None,"board_revisions":revisions,"source_url":source_url,"source_type":"manufacturer_revision_scoped_bios_history","confidence":"high"})
            for child in value.values(): walk(child,revisions)
    walk(payload)
    dedup={}
    for row in rows:
        key=(row["version"].casefold(),tuple(row["board_revisions"]))
        dedup[key]=row
    return list(dedup.values())


def bios_history_for_revision(rows: list[dict[str,Any]], revision: str | None) -> dict[str,Any]:
    if not revision:
        return {"revision":None,"rows":[],"status":"revision_unknown","complete":False}
    target=str(revision).strip().upper().removeprefix("REV.").removeprefix("REV ").strip()
    matched=[]; unscoped=[]
    for row in rows:
        scopes=_revisions(row.get("board_revisions") or row.get("revision"))
        if not scopes: unscoped.append(row)
        elif target in scopes: matched.append(row)
    if matched:
        return {"revision":target,"rows":matched,"status":"revision_scoped","complete":False,"unscoped_rows_ignored":len(unscoped)}
    return {"revision":target,"rows":[],"status":"no_revision_scoped_history","complete":False,"unscoped_rows_ignored":len(unscoped)}
