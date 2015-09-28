ALTER TABLE invoices_invoicepaymentmethod ADD COLUMN internaldescription varchar(100) NOT NULL DEFAULT '';
ALTER TABLE invoices_invoicepaymentmethod ALTER COLUMN internaldescription DROP DEFAULT;

UPDATE invoices_invoicepaymentmethod SET internaldescription='Paypal' WHERE classname='util.payment.paypal.Paypal';
UPDATE invoices_invoicepaymentmethod SET internaldescription='Adyen creditcard' WHERE classname='util.payment.adyen.AdyenCreditcard';
UPDATE invoices_invoicepaymentmethod SET internaldescription='Adyen managed bank transfer' WHERE classname='util.payment.adyen.AdyenBanktransfer';
UPDATE invoices_invoicepaymentmethod SET internaldescription='Manual bank transfer' WHERE classname='util.payment.banktransfer.Banktransfer';
