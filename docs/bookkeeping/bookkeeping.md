# Bookkeeping

The PostgreSQL Europe Conference Management System can be setup to automatically 
handle bookkeeping the bookkeeping of an organization running conferences. 

> **Notice!** This is not a guide to bookkeeping. It is simply a description how
> the bookkeeping of the PostgreSQL Europe Conference Management System can be 
> setup. Please refer to your accountant for information on how to actually do 
> bookkeeping.

The accounting system of the PostgreSQL Europe Conference Management System uses 
the cash basis principle. This is a simplified method of bookkeeping where the 
result of an invoice appears in the books first when it has been paid. To track 
outstanding invoices, a report of unpaid invoices can be generated.

## Accounts

The first step to setup automated accounting is to create accounts to book costs 
to. The accounts are grouped in a hierarcy starting with *Classes*, then 
*Groups*, and finally *Accounts*. Each class can be either a results or a 
balance class, and the sign of the numbers can be inversed or not.

> The accounting setup proposed here is based on the Swedish *Kontoplan BAS 
> 2019*, available from 
> [https://www.srfredovisning.se/kontoplan-bas-2014-2/](https://www.srfredovisning.se/kontoplan-bas-2014-2/). 
> The system is built to support *kontantmetoden*, 
> that is the "cash method". This means that debts are not booked until paid. 
> However, since all invoices are kept in the system, you still have a good 
> overview of any outstanding payments from your customers.

For our conference, we setup a minimal set of accounts. We start with the 
following classes:

Account Class | Balance | Inverted
--- | --- | ---
1. Tillgångar | Y |
2. Eget kapital och skulder | Y |
3. Rörensens inkomster / intäkter | |
5-6. Övriga externa rörelseutgifter / kostnader | |

Under these, we setup the following groups:

Account Group | Account Class
--- | ---
19. Kassa och bank | 1. Tillgångar
25, Skatteskulder | 2. Eget kapital och skulder
26. Moms och särskilda punktskatter | 2. Eget kapital och skulder
30-34. Huvudintäkter | 3. Rörelsense inkomster / intäkter
65. Övriga externa tjänster | 5-6. Övriga externa rörelseutgifter / kostnader

And then we can finally setup the accounts:

Account# | Account Name | Account Group | Available for invoicing
--- | --- | --- | ---
1940 | Bank | TBD | 
1941 | Paypal | TBD | 
1942 | Bankgiro | TBD | 
1943 | Stripe | TBD | 
2611 | Utgående moms på försäljning inom Sverige, 25 % | TBD | 
3001 | Försäljning inom Sverige, 25 % moms | TBD | Y
3002 | Försäljning inom Sverige, 12 % moms | TBD | Y
3003 | Försäljning inom Sverige, 6 % moms | TBD | Y
3004 | Försäljning inom Sverige, momsfri | TBD | Y
6570 | Bankkostnader | TBD | 
6571 | Bankkostnader, stripe | TBD |

Notice that we plan to track different payment methods via different accounts. 
Read more on how to connect individual account to payment methods in the 
[Payment Methods](#paymentmethods) section.

## Creating Invoices

## Tracking Payments

## Payment Methods <a name="paymentmethods"></a>

### Stripe

3 accounts:

- 1942 stripe konto, completed payments
- 6571 bankkonstnad, stripe = fee account = kostnad för avgiften
- 1940 payout account = bankkonto dit banken betalar


## Generating Reports
