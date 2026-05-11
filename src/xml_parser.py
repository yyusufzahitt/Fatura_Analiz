"""
UBL-TR XML e-fatura parser — kapsamlı alan çıkarımı.
GİB TEMELFATURA, TİCARİFATURA ve e-Arşiv formatlarını destekler.
"""
import xml.etree.ElementTree as ET

_CBC = "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"
_CAC = "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"


def _t(ns: str, local: str) -> str:
    return f"{{{ns}}}{local}"


def _text(el) -> str:
    return el.text.strip() if el is not None and el.text else ""


def _attr(el, attr: str, default: str = "") -> str:
    return el.get(attr, default) if el is not None else default


def _build_address(addr_el) -> str:
    """PostalAddress elementinden okunabilir adres oluştur."""
    if addr_el is None:
        return ""
    parts = []
    for field in ["StreetName", "BuildingNumber", "CitySubdivisionName",
                  "CityName", "PostalZone"]:
        val = _text(addr_el.find(_t(_CBC, field)))
        if val:
            parts.append(val)
    country_el = addr_el.find(_t(_CAC, "Country"))
    if country_el is not None:
        code = _text(country_el.find(_t(_CBC, "IdentificationCode")))
        if code and code != "TR":
            parts.append(code)
    return ", ".join(parts)


def _party_name(party_el) -> str:
    """Taraf adını birden fazla yoldan dene."""
    if party_el is None:
        return ""
    for ns, local in [(_CAC, "PartyName"), (_CAC, "PartyTradeName")]:
        pn = party_el.find(_t(ns, local))
        if pn is not None:
            name = _text(pn.find(_t(_CBC, "Name")))
            if name:
                return name
    return ""


def _party_vkn(party_el) -> str:
    """VKN / TCKN — PartyTaxScheme veya PartyIdentification'dan al."""
    if party_el is None:
        return ""
    for scheme in party_el.findall(_t(_CAC, "PartyTaxScheme")):
        cid = _text(scheme.find(_t(_CBC, "CompanyID")))
        if cid:
            return cid
    for ident in party_el.findall(_t(_CAC, "PartyIdentification")):
        cid = _text(ident.find(_t(_CBC, "ID")))
        if cid:
            return cid
    return ""


# ─── Ana parser ───────────────────────────────────────────────────────────────

def parse_ubl_xml(filepath: str) -> dict:
    """
    UBL-TR XML e-faturayı parse eder.
    Dönen sözlük, database.py'deki save_invoice() ile doğrudan uyumludur.
    """
    try:
        tree = ET.parse(filepath)
        root = tree.getroot()

        # ── Kimlik & belge ────────────────────────────────────────────────────
        invoice_number = _text(root.find(_t(_CBC, "ID")))
        invoice_date   = _text(root.find(_t(_CBC, "IssueDate")))
        currency       = _text(root.find(_t(_CBC, "DocumentCurrencyCode"))) or "TRY"

        profile_id   = _text(root.find(_t(_CBC, "ProfileID")))
        invoice_type = {
            "TEMELFATURA":  "e-Fatura (Temel)",
            "TICARIFATURA": "e-Fatura (Ticari)",
            "EARSIVFATURA": "e-Arşiv Fatura",
        }.get((profile_id or "").upper(), profile_id or "")

        ref_el = root.find(_t(_CAC, "OrderReference"))
        reference_number = (
            _text(ref_el.find(_t(_CBC, "ID"))) if ref_el is not None else ""
        )

        # ── Ödeme bilgisi ─────────────────────────────────────────────────────
        due_date = payment_method = iban = ""
        pm_el = root.find(_t(_CAC, "PaymentMeans"))
        if pm_el is not None:
            due_date       = _text(pm_el.find(_t(_CBC, "PaymentDueDate")))
            payment_method = _text(pm_el.find(_t(_CBC, "PaymentMeansCode")))
            acc_el = pm_el.find(_t(_CAC, "PayeeFinancialAccount"))
            if acc_el is not None:
                iban = _text(acc_el.find(_t(_CBC, "ID")))

        # PaymentTerms içinde vade tarihi olabilir
        if not due_date:
            pt_el = root.find(_t(_CAC, "PaymentTerms"))
            if pt_el is not None:
                due_date = _text(pt_el.find(_t(_CBC, "PaymentDueDate")))

        # ── Satıcı ────────────────────────────────────────────────────────────
        vendor_name = vendor_vkn = vendor_address = ""
        supplier_el = root.find(_t(_CAC, "AccountingSupplierParty"))
        if supplier_el is not None:
            party = supplier_el.find(_t(_CAC, "Party"))
            if party is not None:
                vendor_name    = _party_name(party)
                vendor_vkn     = _party_vkn(party)
                vendor_address = _build_address(party.find(_t(_CAC, "PostalAddress")))

        # ── Alıcı ─────────────────────────────────────────────────────────────
        buyer_name = buyer_vkn = buyer_address = ""
        customer_el = root.find(_t(_CAC, "AccountingCustomerParty"))
        if customer_el is not None:
            party = customer_el.find(_t(_CAC, "Party"))
            if party is not None:
                buyer_name    = _party_name(party)
                buyer_vkn     = _party_vkn(party)
                buyer_address = _build_address(party.find(_t(_CAC, "PostalAddress")))

        # ── Çoklu KDV satırları (%1 / %8 / %18 / %20 ayrı ayrı) ─────────────
        tax_lines  = []
        total_tax  = 0.0
        for tt in root.findall(_t(_CAC, "TaxTotal")):
            for sub in tt.findall(_t(_CAC, "TaxSubtotal")):
                t_base   = _text(sub.find(_t(_CBC, "TaxableAmount")))
                t_amount = _text(sub.find(_t(_CBC, "TaxAmount")))
                t_rate   = ""
                cat_el = sub.find(_t(_CAC, "TaxCategory"))
                if cat_el is not None:
                    t_rate = _text(cat_el.find(_t(_CBC, "Percent")))
                tax_lines.append({
                    "tax_rate":   t_rate,
                    "tax_base":   t_base,
                    "tax_amount": t_amount,
                })
                try:
                    total_tax += float(t_amount) if t_amount else 0.0
                except ValueError:
                    pass

        tax_amount = f"{total_tax:.2f}" if total_tax > 0 else ""

        # Genel KDV oranı: en yüksek oran
        tax_rate = ""
        rates = [tl["tax_rate"] for tl in tax_lines if tl.get("tax_rate")]
        if rates:
            try:
                tax_rate = str(max(rates, key=lambda r: float(r)))
            except ValueError:
                tax_rate = rates[0]

        # ── Tutarlar ──────────────────────────────────────────────────────────
        subtotal = discount_amount = total = ""
        lmt = root.find(_t(_CAC, "LegalMonetaryTotal"))
        if lmt is not None:
            subtotal        = _text(lmt.find(_t(_CBC, "LineExtensionAmount")))
            discount_amount = _text(lmt.find(_t(_CBC, "AllowanceTotalAmount")))
            total = (
                _text(lmt.find(_t(_CBC, "PayableAmount"))) or
                _text(lmt.find(_t(_CBC, "TaxInclusiveAmount")))
            )

        # ── Kalem satırları ───────────────────────────────────────────────────
        line_items = []
        for line in root.findall(_t(_CAC, "InvoiceLine")):
            qty_el = line.find(_t(_CBC, "InvoicedQuantity"))
            qty    = _text(qty_el)
            unit   = _attr(qty_el, "unitCode")
            amount = _text(line.find(_t(_CBC, "LineExtensionAmount")))

            desc = product_code = ""
            item_el = line.find(_t(_CAC, "Item"))
            if item_el is not None:
                desc = _text(item_el.find(_t(_CBC, "Name")))
                sid  = item_el.find(_t(_CAC, "SellersItemIdentification"))
                if sid is not None:
                    product_code = _text(sid.find(_t(_CBC, "ID")))

            unit_price = ""
            price_el = line.find(_t(_CAC, "Price"))
            if price_el is not None:
                unit_price = _text(price_el.find(_t(_CBC, "PriceAmount")))

            line_tax_rate = line_tax_amount = ""
            lt_el = line.find(_t(_CAC, "TaxTotal"))
            if lt_el is not None:
                line_tax_amount = _text(lt_el.find(_t(_CBC, "TaxAmount")))
                sub_el = lt_el.find(_t(_CAC, "TaxSubtotal"))
                if sub_el is not None:
                    cat_el = sub_el.find(_t(_CAC, "TaxCategory"))
                    if cat_el is not None:
                        line_tax_rate = _text(cat_el.find(_t(_CBC, "Percent")))

            line_discount_rate = ""
            for ac in line.findall(_t(_CAC, "AllowanceCharge")):
                if _text(ac.find(_t(_CBC, "ChargeIndicator"))) == "false":
                    line_discount_rate = _text(
                        ac.find(_t(_CBC, "MultiplierFactorNumeric"))
                    )
                    break

            line_items.append({
                "description":   desc,
                "qty":           qty,
                "unit":          unit,
                "unit_price":    unit_price,
                "discount_rate": line_discount_rate,
                "tax_rate":      line_tax_rate,
                "tax_amount":    line_tax_amount,
                "amount":        amount,
                "product_code":  product_code,
            })

        return {
            "_source":          "xml",
            "invoice_number":   invoice_number,
            "invoice_date":     invoice_date,
            "due_date":         due_date,
            "reference_number": reference_number,
            "invoice_type":     invoice_type,
            "currency":         currency,
            "vendor_name":      vendor_name,
            "vendor_vkn":       vendor_vkn,
            "vendor_address":   vendor_address,
            "buyer_name":       buyer_name,
            "buyer_vkn":        buyer_vkn,
            "buyer_address":    buyer_address,
            "subtotal":         subtotal,
            "discount_amount":  discount_amount,
            "tax_amount":       tax_amount,
            "tax_rate":         tax_rate,
            "total":            total,
            "payment_method":   payment_method,
            "iban":             iban,
            "tax_lines":        tax_lines,
            "line_items":       line_items,
        }

    except Exception as e:
        return {"parse_error": str(e), "_source": "xml"}
