<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet version="1.0"
  xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
  xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
  xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"
  exclude-result-prefixes="cac cbc">

  <xsl:output method="html" encoding="UTF-8" indent="yes"/>

  <!-- ═══════════════════════════════════════════════════════════════ -->
  <!--  Kök şablon                                                     -->
  <!-- ═══════════════════════════════════════════════════════════════ -->
  <xsl:template match="/">
    <div class="xslt-invoice">
      <style>
        .xslt-invoice {
          font-family: 'Segoe UI', Arial, sans-serif;
          font-size: 13px;
          color: #1a1a2e;
          background: #fff;
          max-width: 860px;
          margin: 0 auto;
          padding: 32px;
          border-radius: 12px;
          box-shadow: 0 2px 24px rgba(0,0,0,0.10);
        }
        /* ── Başlık ── */
        .xi-header {
          display: flex;
          justify-content: space-between;
          align-items: flex-start;
          border-bottom: 2px solid #7c3aed;
          padding-bottom: 18px;
          margin-bottom: 24px;
        }
        .xi-title { font-size: 22px; font-weight: 800; color: #7c3aed; }
        .xi-meta  { text-align: right; }
        .xi-badge {
          display: inline-block;
          background: linear-gradient(135deg, #7c3aed, #ec4899);
          color: #fff;
          font-size: 11px;
          font-weight: 700;
          padding: 3px 12px;
          border-radius: 20px;
          letter-spacing: 0.5px;
          margin-bottom: 6px;
        }
        .xi-no   { font-size: 15px; font-weight: 700; color: #1a1a2e; }
        .xi-date { font-size: 12px; color: #666; margin-top: 2px; }
        /* ── Taraflar ── */
        .xi-parties {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 16px;
          margin-bottom: 24px;
        }
        .xi-party {
          background: #f8f7ff;
          border: 1px solid #e0d9ff;
          border-radius: 8px;
          padding: 14px 16px;
        }
        .xi-party-label {
          font-size: 10px;
          font-weight: 700;
          text-transform: uppercase;
          letter-spacing: 1px;
          color: #7c3aed;
          margin-bottom: 8px;
        }
        .xi-party-name { font-size: 14px; font-weight: 700; color: #1a1a2e; }
        .xi-party-detail { font-size: 12px; color: #555; margin-top: 3px; line-height: 1.5; }
        /* ── Kalemler ── */
        .xi-table {
          width: 100%;
          border-collapse: collapse;
          margin-bottom: 20px;
          font-size: 12px;
        }
        .xi-table th {
          background: #7c3aed;
          color: #fff;
          text-align: left;
          padding: 8px 10px;
          font-size: 11px;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.5px;
        }
        .xi-table th:last-child, .xi-table td:last-child { text-align: right; }
        .xi-table td {
          padding: 8px 10px;
          border-bottom: 1px solid #f0eeff;
          color: #333;
        }
        .xi-table tr:nth-child(even) td { background: #faf9ff; }
        /* ── Vergi özeti ── */
        .xi-tax-table {
          width: 100%;
          border-collapse: collapse;
          margin-bottom: 20px;
          font-size: 12px;
        }
        .xi-tax-table th {
          background: #f0eeff;
          color: #7c3aed;
          padding: 7px 10px;
          text-align: right;
          font-size: 11px;
          font-weight: 700;
          text-transform: uppercase;
        }
        .xi-tax-table th:first-child { text-align: left; }
        .xi-tax-table td {
          padding: 6px 10px;
          border-bottom: 1px solid #f0eeff;
          text-align: right;
          color: #333;
        }
        .xi-tax-table td:first-child { text-align: left; }
        /* ── Toplamlar ── */
        .xi-totals { margin-left: auto; width: 320px; margin-bottom: 24px; }
        .xi-total-row {
          display: flex;
          justify-content: space-between;
          padding: 5px 0;
          border-bottom: 1px solid #f0eeff;
          font-size: 13px;
          color: #333;
        }
        .xi-total-row.grand {
          font-weight: 800;
          font-size: 16px;
          color: #7c3aed;
          border-bottom: none;
          border-top: 2px solid #7c3aed;
          padding-top: 10px;
          margin-top: 4px;
        }
        /* ── Ödeme ── */
        .xi-payment {
          background: #f8f7ff;
          border: 1px solid #e0d9ff;
          border-radius: 8px;
          padding: 12px 16px;
          font-size: 12px;
          color: #555;
          margin-bottom: 16px;
        }
        .xi-payment strong { color: #7c3aed; }
        /* ── Footer ── */
        .xi-footer {
          text-align: center;
          font-size: 10px;
          color: #aaa;
          border-top: 1px solid #eee;
          padding-top: 12px;
          margin-top: 8px;
        }
        /* ── Bölüm başlığı ── */
        .xi-section-title {
          font-size: 11px;
          font-weight: 700;
          text-transform: uppercase;
          letter-spacing: 1px;
          color: #7c3aed;
          margin: 20px 0 8px;
        }
      </style>

      <xsl:apply-templates select="//*[local-name()='Invoice']"/>
    </div>
  </xsl:template>

  <!-- ═══════════════════════════════════════════════════════════════ -->
  <!--  Invoice şablonu                                                -->
  <!-- ═══════════════════════════════════════════════════════════════ -->
  <xsl:template match="*[local-name()='Invoice']">

    <!-- BAŞLIK -->
    <div class="xi-header">
      <div>
        <div class="xi-title">E-FATURA</div>
        <div style="font-size:12px;color:#888;margin-top:4px;">
          Invoice Auditor — Resmi Görüntüleyici
        </div>
      </div>
      <div class="xi-meta">
        <xsl:if test="cbc:ProfileID">
          <div>
            <span class="xi-badge">
              <xsl:choose>
                <xsl:when test="cbc:ProfileID='TICARIFATURA'">e-Fatura Ticari</xsl:when>
                <xsl:when test="cbc:ProfileID='TEMELFATURA'">e-Fatura Temel</xsl:when>
                <xsl:when test="cbc:ProfileID='EARSIVFATURA'">e-Arşiv Fatura</xsl:when>
                <xsl:otherwise><xsl:value-of select="cbc:ProfileID"/></xsl:otherwise>
              </xsl:choose>
            </span>
          </div>
        </xsl:if>
        <div class="xi-no">No: <xsl:value-of select="cbc:ID"/></div>
        <div class="xi-date">
          Tarih: <xsl:value-of select="cbc:IssueDate"/>
          <xsl:if test="cac:PaymentMeans/cbc:PaymentDueDate">
            &#160;&#160;|&#160;&#160;Vade: <xsl:value-of select="cac:PaymentMeans/cbc:PaymentDueDate"/>
          </xsl:if>
        </div>
        <xsl:if test="cac:OrderReference/cbc:ID">
          <div class="xi-date">Sipariş No: <xsl:value-of select="cac:OrderReference/cbc:ID"/></div>
        </xsl:if>
        <div class="xi-date">
          Para Birimi: <xsl:value-of select="cbc:DocumentCurrencyCode"/>
        </div>
      </div>
    </div>

    <!-- TARAFLAR -->
    <div class="xi-parties">
      <!-- Satıcı -->
      <div class="xi-party">
        <div class="xi-party-label">Satıcı</div>
        <div class="xi-party-name">
          <xsl:value-of select="cac:AccountingSupplierParty/cac:Party/cac:PartyName/cbc:Name"/>
        </div>
        <xsl:if test="cac:AccountingSupplierParty/cac:Party/cac:PartyTaxScheme/cbc:CompanyID">
          <div class="xi-party-detail">
            VKN: <xsl:value-of select="cac:AccountingSupplierParty/cac:Party/cac:PartyTaxScheme/cbc:CompanyID"/>
          </div>
        </xsl:if>
        <xsl:if test="cac:AccountingSupplierParty/cac:Party/cac:PostalAddress/cbc:CityName">
          <div class="xi-party-detail">
            <xsl:value-of select="cac:AccountingSupplierParty/cac:Party/cac:PostalAddress/cbc:StreetName"/>
            <xsl:if test="cac:AccountingSupplierParty/cac:Party/cac:PostalAddress/cbc:StreetName">, </xsl:if>
            <xsl:value-of select="cac:AccountingSupplierParty/cac:Party/cac:PostalAddress/cbc:CityName"/>
          </div>
        </xsl:if>
      </div>
      <!-- Alıcı -->
      <div class="xi-party">
        <div class="xi-party-label">Alıcı</div>
        <xsl:choose>
          <xsl:when test="cac:AccountingCustomerParty/cac:Party/cac:PartyName/cbc:Name">
            <div class="xi-party-name">
              <xsl:value-of select="cac:AccountingCustomerParty/cac:Party/cac:PartyName/cbc:Name"/>
            </div>
            <xsl:if test="cac:AccountingCustomerParty/cac:Party/cac:PartyTaxScheme/cbc:CompanyID">
              <div class="xi-party-detail">
                VKN: <xsl:value-of select="cac:AccountingCustomerParty/cac:Party/cac:PartyTaxScheme/cbc:CompanyID"/>
              </div>
            </xsl:if>
            <xsl:if test="cac:AccountingCustomerParty/cac:Party/cac:PostalAddress/cbc:CityName">
              <div class="xi-party-detail">
                <xsl:value-of select="cac:AccountingCustomerParty/cac:Party/cac:PostalAddress/cbc:StreetName"/>
                <xsl:if test="cac:AccountingCustomerParty/cac:Party/cac:PostalAddress/cbc:StreetName">, </xsl:if>
                <xsl:value-of select="cac:AccountingCustomerParty/cac:Party/cac:PostalAddress/cbc:CityName"/>
              </div>
            </xsl:if>
          </xsl:when>
          <xsl:otherwise>
            <div class="xi-party-detail" style="color:#aaa;font-style:italic;">Alıcı bilgisi yok</div>
          </xsl:otherwise>
        </xsl:choose>
      </div>
    </div>

    <!-- KALEM SATIRLARI -->
    <xsl:if test="cac:InvoiceLine">
      <div class="xi-section-title">Kalemler</div>
      <table class="xi-table">
        <thead>
          <tr>
            <th>#</th>
            <th>Ürün / Hizmet</th>
            <th>Miktar</th>
            <th>Birim Fiyat</th>
            <th>KDV %</th>
            <th>Tutar</th>
          </tr>
        </thead>
        <tbody>
          <xsl:for-each select="cac:InvoiceLine">
            <tr>
              <td><xsl:value-of select="cbc:ID"/></td>
              <td><xsl:value-of select="cac:Item/cbc:Name"/></td>
              <td>
                <xsl:value-of select="cbc:InvoicedQuantity"/>
                <xsl:if test="cbc:InvoicedQuantity/@unitCode">
                  &#160;<xsl:value-of select="cbc:InvoicedQuantity/@unitCode"/>
                </xsl:if>
              </td>
              <td><xsl:value-of select="cac:Price/cbc:PriceAmount"/></td>
              <td>
                <xsl:value-of select="cac:TaxTotal/cac:TaxSubtotal/cac:TaxCategory/cbc:Percent"/>
                <xsl:if test="cac:TaxTotal/cac:TaxSubtotal/cac:TaxCategory/cbc:Percent">%</xsl:if>
              </td>
              <td><xsl:value-of select="cbc:LineExtensionAmount"/></td>
            </tr>
          </xsl:for-each>
        </tbody>
      </table>
    </xsl:if>

    <!-- KDV OZETI -->
    <xsl:if test="cac:TaxTotal/cac:TaxSubtotal">
      <div class="xi-section-title">Vergi Özeti</div>
      <table class="xi-tax-table">
        <thead>
          <tr>
            <th>Vergi Türü</th>
            <th>Oran</th>
            <th>Matrah</th>
            <th>Vergi Tutarı</th>
          </tr>
        </thead>
        <tbody>
          <xsl:for-each select="cac:TaxTotal/cac:TaxSubtotal">
            <tr>
              <td>KDV</td>
              <td>%<xsl:value-of select="cac:TaxCategory/cbc:Percent"/></td>
              <td><xsl:value-of select="cbc:TaxableAmount"/>&#160;<xsl:value-of select="../../cbc:DocumentCurrencyCode"/></td>
              <td><xsl:value-of select="cbc:TaxAmount"/>&#160;<xsl:value-of select="../../cbc:DocumentCurrencyCode"/></td>
            </tr>
          </xsl:for-each>
        </tbody>
      </table>
    </xsl:if>

    <!-- TOPLAMLAR -->
    <div class="xi-totals">
      <xsl:if test="cac:LegalMonetaryTotal/cbc:LineExtensionAmount">
        <div class="xi-total-row">
          <span>Ara Toplam</span>
          <span>
            <xsl:value-of select="cac:LegalMonetaryTotal/cbc:LineExtensionAmount"/>
            &#160;<xsl:value-of select="cbc:DocumentCurrencyCode"/>
          </span>
        </div>
      </xsl:if>
      <xsl:if test="cac:LegalMonetaryTotal/cbc:AllowanceTotalAmount">
        <div class="xi-total-row">
          <span>İskonto</span>
          <span style="color:#e53e3e;">
            -<xsl:value-of select="cac:LegalMonetaryTotal/cbc:AllowanceTotalAmount"/>
            &#160;<xsl:value-of select="cbc:DocumentCurrencyCode"/>
          </span>
        </div>
      </xsl:if>
      <xsl:if test="cac:TaxTotal/cbc:TaxAmount">
        <div class="xi-total-row">
          <span>Toplam KDV</span>
          <span>
            <xsl:value-of select="cac:TaxTotal/cbc:TaxAmount"/>
            &#160;<xsl:value-of select="cbc:DocumentCurrencyCode"/>
          </span>
        </div>
      </xsl:if>
      <div class="xi-total-row grand">
        <span>GENEL TOPLAM</span>
        <span>
          <xsl:value-of select="cac:LegalMonetaryTotal/cbc:PayableAmount"/>
          &#160;<xsl:value-of select="cbc:DocumentCurrencyCode"/>
        </span>
      </div>
    </div>

    <!-- ÖDEME BİLGİSİ -->
    <xsl:if test="cac:PaymentMeans">
      <div class="xi-payment">
        <strong>Ödeme Bilgisi:</strong>&#160;
        <xsl:if test="cac:PaymentMeans/cbc:PaymentMeansCode">
          Yöntem: <xsl:value-of select="cac:PaymentMeans/cbc:PaymentMeansCode"/>&#160;&#160;
        </xsl:if>
        <xsl:if test="cac:PaymentMeans/cbc:PaymentDueDate">
          Vade: <xsl:value-of select="cac:PaymentMeans/cbc:PaymentDueDate"/>&#160;&#160;
        </xsl:if>
        <xsl:if test="cac:PaymentMeans/cac:PayeeFinancialAccount/cbc:ID">
          IBAN: <strong><xsl:value-of select="cac:PaymentMeans/cac:PayeeFinancialAccount/cbc:ID"/></strong>
        </xsl:if>
      </div>
    </xsl:if>

    <!-- FOOTER -->
    <div class="xi-footer">
      Bu görüntü Invoice Auditor tarafından UBL-TR XML verisinden XSLT dönüşümü ile oluşturulmuştur.
    </div>

  </xsl:template>

</xsl:stylesheet>
