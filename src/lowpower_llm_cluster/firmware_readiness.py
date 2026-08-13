from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlparse

from .bios_versioning import shipped_bios_meets_requirement
from .seller_firmware import correlate_seller_firmware


class _LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(); self.links=[]; self._href=None; self._chunks=[]
    def handle_starttag(self,tag,attrs):
        if tag.casefold()!="a": return
        values={k.casefold():(v or "") for k,v in attrs}
        if values.get("href"): self._href=values["href"]; self._chunks=[]
    def handle_data(self,data):
        if self._href is not None: self._chunks.append(data)
    def handle_endtag(self,tag):
        if tag.casefold()=="a" and self._href is not None: self.links.append({"href":self._href,"text":" ".join("".join(self._chunks).split())}); self._href=None; self._chunks=[]


def _host_allowed(url,official_hosts):
    host=(urlparse(url).hostname or "").casefold(); return any(host==allowed or host.endswith("."+allowed) for allowed in official_hosts)


def discover_support_endpoints(html,base_url,official_hosts=None):
    parser=_LinkParser(); parser.feed(html); base_host=(urlparse(base_url).hostname or "").casefold(); allowed={h.casefold() for h in (official_hosts or {base_host}) if h}; out=[]
    for link in parser.links:
        url=urljoin(base_url,link["href"])
        if not url.startswith("https://") or not _host_allowed(url,allowed): continue
        text=f"{link.get('text','')} {urlparse(url).path}".casefold(); score=0; kinds=[]
        if any(term in text for term in ("cpu support","processor support","cpu-support","support list")): score+=60; kinds.append("cpu_support")
        if any(term in text for term in ("bios","uefi","firmware")): score+=45; kinds.append("bios")
        if any(term in text for term in ("download","support")): score+=20; kinds.append("downloads")
        if any(term in text for term in ("manual","faq","driver")): score+=5
        if score>=20: out.append({"url":url,"score":score,"kinds":sorted(set(kinds)),"anchor_text":link.get("text") or ""})
    dedup={}
    for row in out:
        if row["url"] not in dedup or row["score"]>dedup[row["url"]]["score"]: dedup[row["url"]]=row
    return sorted(dedup.values(),key=lambda row:(-int(row["score"]),row["url"]))[:12]


FLASHBACK_PATTERNS=((r"\bUSB BIOS FlashBack\b","USB BIOS FlashBack"),(r"\bBIOS FlashBack(?: Button)?\b","BIOS FlashBack"),(r"\bFlash BIOS Button\b","Flash BIOS Button"),(r"\bQ[- ]Flash Plus\b","Q-Flash Plus"),(r"\bBIOS Flash Button\b","BIOS Flash Button"))
SHIPPED_BIOS_PATTERNS=(r"(?:ships?|shipped|factory|preinstalled|pre-installed)\s+(?:with\s+)?(?:bios|uefi)\s*(?:version)?\s*[:#-]?\s*([A-Z0-9._-]+)",r"(?:bios|uefi)\s*(?:version)?\s*([A-Z0-9._-]+)\s*(?:or later\s*)?(?:installed|preinstalled|from factory)")


def _explicit_shipped_bios(text: str) -> str | None:
    for pattern in SHIPPED_BIOS_PATTERNS:
        match=re.search(pattern,text,re.IGNORECASE)
        if match: return match.group(1).rstrip(". ,;:)")
    return None


def detect_bios_flashback(text: str) -> dict[str,Any]:
    normalized=" ".join(str(text or "").split()); shipped=_explicit_shipped_bios(normalized)
    for pattern,name in FLASHBACK_PATTERNS:
        if re.search(pattern,normalized,re.IGNORECASE):
            cpu_less=bool(re.search(r"without (?:a |the )?(?:cpu|processor)|no cpu required|without installing (?:a |the )?(?:cpu|processor)",normalized,re.IGNORECASE))
            return {"status":"supported","feature_name":name,"cpu_less_update_explicit":cpu_less,"confidence":"high" if cpu_less else "medium","shipped_bios_version":shipped,"shipped_bios_source":"explicit_manufacturer_text" if shipped else None}
    explicit_no=re.search(r"(?:does not support|without)\s+(?:usb )?(?:bios flashback|q[- ]flash plus|flash bios button)",normalized,re.IGNORECASE)
    if explicit_no: return {"status":"unsupported","feature_name":None,"cpu_less_update_explicit":False,"confidence":"high","shipped_bios_version":shipped,"shipped_bios_source":"explicit_manufacturer_text" if shipped else None}
    return {"status":"unknown","feature_name":None,"cpu_less_update_explicit":None,"confidence":"unknown","shipped_bios_version":shipped,"shipped_bios_source":"explicit_manufacturer_text" if shipped else None}


def boot_readiness_score(cpu_bios: dict[str,Any], flashback: dict[str,Any] | None=None, *, shipped_bios_meets_minimum: bool | None=None) -> dict[str,Any]:
    pair_status=str(cpu_bios.get("status") or "unresolved"); minimum=cpu_bios.get("minimum_bios_version"); flashback=flashback or {"status":"unknown","cpu_less_update_explicit":None}; fb_status=str(flashback.get("status") or "unknown"); cpu_less=flashback.get("cpu_less_update_explicit") is True; warnings=[]
    shipped_version=flashback.get("shipped_bios_version"); version_comparison=None
    if shipped_bios_meets_minimum is None and minimum and shipped_version:
        version_comparison=shipped_bios_meets_requirement(str(shipped_version),str(minimum),source_url=cpu_bios.get("source_url") or flashback.get("source_url"),provider=cpu_bios.get("provider"))
        shipped_bios_meets_minimum=version_comparison.get("meets_minimum")
        if shipped_bios_meets_minimum is None: warnings.append(f"Board explicitly ships with BIOS {shipped_version}, but safe vendor-specific version ordering against required {minimum} is unresolved.")
        elif shipped_bios_meets_minimum is False: warnings.append(f"Board explicitly ships with BIOS {shipped_version}, which is older than required {minimum} by {version_comparison.get('reason')}.")

    seller_firmware=correlate_seller_firmware(cpu_bios,flashback.get("seller_firmware_evidence"),flashback.get("revision_bios_history") or [])
    seller_meets=seller_firmware.get("meets_minimum")
    seller_history_match=seller_firmware.get("installed_bios_in_revision_history") is True
    factory_firmware=dict(seller_firmware.get("factory_firmware") or {})
    factory_meets=factory_firmware.get("meets_minimum")
    if factory_firmware.get("status")=="verified_factory_firmware":
        if factory_meets is True:
            warnings.append(f"Manufacturer-published factory firmware evidence resolves this board to BIOS {factory_firmware.get('factory_bios_version')}, satisfying required {minimum}.")
        elif factory_meets is False:
            warnings.append(f"Manufacturer-published factory firmware evidence resolves this board to BIOS {factory_firmware.get('factory_bios_version')}, below required {minimum}; an update is required before first boot with the selected CPU.")
        else:
            warnings.append("Manufacturer-published factory firmware evidence matched, but safe ordering against the required BIOS is unresolved.")
    if seller_firmware.get("installed_bios_version"):
        if seller_meets is True and seller_history_match:
            warnings.append("Seller-stated installed BIOS meets the CPU minimum and exists in official BIOS history for the seller-stated board revision; seller evidence remains lower authority than manufacturer factory evidence.")
        elif seller_meets is True:
            warnings.append("Seller-stated installed BIOS meets the CPU minimum by vendor-safe version comparison, but revision-scoped manufacturer history did not independently verify that exact installed version.")
        elif seller_meets is False:
            warnings.append(f"Seller-stated installed BIOS {seller_firmware.get('installed_bios_version')} is below required {minimum}; firmware update is required before using the selected CPU.")
        else:
            warnings.append("Seller states an installed BIOS version, but safe vendor-specific ordering against the CPU minimum is unresolved.")

    if pair_status=="unsupported": score=0; readiness="not_bootable_with_selected_cpu"
    elif pair_status=="supported" and not minimum: score=96; readiness="ready_by_support_evidence"
    elif pair_status=="supported" and minimum:
        if shipped_bios_meets_minimum is True: score=98; readiness="ready_with_verified_firmware"
        elif factory_meets is True: score=98; readiness="ready_with_verified_factory_firmware"
        elif seller_meets is True and seller_history_match: score=94; readiness="ready_by_correlated_seller_installed_firmware"
        elif seller_meets is True: score=90; readiness="ready_by_seller_installed_firmware_claim"
        elif cpu_less: score=88; readiness="supported_update_may_be_required_cpu_less_recovery_available"; warnings.append(f"CPU requires BIOS >= {minimum}; CPU-less update capability is explicitly documented.")
        elif fb_status=="supported": score=78; readiness="supported_update_may_be_required_flashback_detected"; warnings.append(f"CPU requires BIOS >= {minimum}; firmware update capability is documented but CPU-less operation was not explicitly verified.")
        elif fb_status=="unsupported": score=48; readiness="supported_but_update_path_has_high_friction"; warnings.append(f"CPU requires BIOS >= {minimum}; no CPU-less firmware-update path is documented by current evidence.")
        else: score=62; readiness="supported_but_shipped_bios_and_recovery_unknown"; warnings.append(f"CPU requires BIOS >= {minimum}; shipped BIOS and CPU-less recovery capability are unknown or insufficient.")
    else:
        score=54 if cpu_less else 34; readiness="support_unresolved_but_cpu_less_recovery_available" if cpu_less else "support_and_boot_path_unresolved"; warnings.append(str(cpu_bios.get("reason") or "CPU/BIOS support is unresolved."))
    if cpu_bios.get("matrix_complete") is False and pair_status=="unresolved": warnings.append("Manufacturer CPU-support matrix is not proven complete; absence is not treated as unsupported.")
    return {"score":int(score),"readiness":readiness,"cpu_bios_status":pair_status,"minimum_bios_version":minimum,"flashback_status":fb_status,"cpu_less_update_explicit":flashback.get("cpu_less_update_explicit"),"shipped_bios_version":shipped_version,"shipped_bios_meets_minimum":shipped_bios_meets_minimum,"version_comparison":version_comparison,"factory_firmware":factory_firmware,"seller_firmware":seller_firmware,"warnings":warnings,"basis":"manufacturer_cpu_support_plus_factory_firmware_recovery_and_bounded_seller_evidence","performance_claim":False}
