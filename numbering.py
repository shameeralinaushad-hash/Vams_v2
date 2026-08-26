from datetime import datetime


def build_quotation_number(company, client, raw_number):
    short = (company.short_name or company.name).lower()
    location = company.location_code or "ISB"
    code = client.client_code or (client.name[:3].upper() if client.name else "CLT")
    year = datetime.utcnow().year
    return f"{short}/{location}/{code}/{year}/{raw_number}"


def build_technical_offer_number(company, client, raw_number):
    short = (company.short_name or company.name).lower()
    location = company.location_code or "ISB"
    code = client.client_code or (client.name[:3].upper() if client.name else "CLT")
    year = datetime.utcnow().year
    return f"{short}/{location}/{code}/T-{year}/{raw_number}"


def build_invoice_number(company, client, raw_number):
    short = company.short_name or company.name
    code = client.client_code or (client.name[:3].upper() if client.name else "CLT")
    year = datetime.utcnow().year
    return f"{short}/{code}/{year}{raw_number:05d}"


def build_challan_number(company, client, raw_number):
    short = company.short_name or company.name
    code = client.client_code or (client.name[:3].upper() if client.name else "CLT")
    year = datetime.utcnow().year
    return f"{short}/{code}/{year}{raw_number:05d}"