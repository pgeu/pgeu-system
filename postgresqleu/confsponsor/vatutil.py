import requests

def validate_eu_vat_number(number):
    country = number[:2]
    number = number[2:]

    try:
        r = requests.post('http://ec.europa.eu/taxation_customs/vies/vatResponse.html', data={
            'memberStateCode': country,
            'number': number,
            'traderName': '',
            'traderCompanyType': '',
            'traderStreet': '',
            'traderPostalCode': '',
        }, timeout=15)
        if '<span class="validStyle">Yes, valid VAT number</span>' in r.text:
            return None
        return "Invalid VAT number according to validation service"
    except:
        return "Unable to reach validation service"
