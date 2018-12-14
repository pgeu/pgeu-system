from benefitclasses import all_benefits

benefit_choices = [(k, v['name']) for k, v in all_benefits.items()]

def get_benefit_class(benefitid):
    return all_benefits[benefitid]['class']
