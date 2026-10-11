"""Specialist catalog describes capabilities; case reasoning chooses the subset."""
PACKS = {
    'CONSUMER': {
        'CONSUMER_DOMAIN': 'Assess consumer relationship uncertainty without assuming eligibility.',
        'TRANSACTION': 'Identify consideration, goods/services and transaction relationships.',
        'PRODUCT_DEFECT': 'Structure alleged defect/deficiency and unknown causes.',
        'WARRANTY_REFUND_REPLACEMENT': 'Separate stated warranties and requested relief from legal entitlement.',
        'CONSUMER_EVIDENCE': 'Identify consumer issue evidence and missing support.',
        'CONSUMER_REMEDY': 'Identify requested outcomes; no entitlement without retrieved authority.',
    },
    'LABOUR_EMPLOYMENT': {
        'LABOUR_DOMAIN': 'Assess employment context and classification uncertainty.',
        'EMPLOYMENT_RELATIONSHIP': 'Separate employee, contractor, intern and gig relationship evidence.',
        'WAGE_ENTITLEMENT': 'Identify claimed unpaid wages, periods and disputed entitlement.',
        'EMPLOYMENT_DOCUMENT': 'Read only provided employment terms and document references.',
        'WAGE_EVIDENCE': 'Map payment/attendance facts and missing evidence.',
        'EMPLOYMENT_REMEDY': 'Identify requested employment relief pending verified legal basis.',
    },
    'PROPERTY_TENANCY': {
        'PROPERTY_DOMAIN': 'Separate ownership, possession and tenancy issues.',
        'OWNERSHIP_TITLE': 'Analyse stated title chain without inferring ownership from possession.',
        'PROPERTY_DOCUMENT': 'Identify supplied deeds/leases and documentary gaps.',
        'LAND_RECORDS': 'Identify required land records and whether actually available.',
        'POSSESSION': 'Structure possession facts separately from title.',
        'BOUNDARY_SURVEY': 'Analyse supported boundary/survey dispute only.',
        'RENT_DEPOSIT': 'Structure rental payments, deposit and withholding facts.',
    },
    'CRIMINAL_POLICE': {
        'CRIMINAL_DOMAIN': 'Identify alleged incident and procedural context; do not assume guilt.',
        'CRIMINAL_INCIDENT': 'Structure incident, participants and disputed facts.',
        'OFFENCE_MAPPING': 'Identify factual offence questions; Sections must await retrieved law.',
        'FIR_COMPLAINT': 'Distinguish reported complaint, FIR and unknown procedural records.',
        'LEGAL_INGREDIENT': 'Identify factual element questions; legal ingredients await verified source.',
        'DIGITAL_EVIDENCE': 'Identify actual digital records and authenticity gaps.',
        'MEDICAL_EVIDENCE': 'Identify actual medical records and unknown injury details.',
        'WITNESS': 'Identify source-stated witnesses; never invent testimony.',
    },
    'CIVIL_CONTRACT': {
        'CONTRACT_RELATIONSHIP': 'Identify supported contracting relationships.',
        'CLAUSE': 'Analyse only clauses supplied or explicitly stated, with uncertainty retained.',
        'PERFORMANCE_BREACH': 'Separate promised performance, actual performance and alleged breach.',
        'PAYMENT': 'Structure payments, amounts and disputed invoices.',
        'DAMAGES_RELIEF': 'Identify claimed loss and desired relief without inventing entitlement.',
        'NOTICE': 'Identify notices actually sent/received and missing service proof.',
    },
    'RTI_ADMINISTRATIVE': {
        'PUBLIC_AUTHORITY': 'Identify stated public authority and missing identification.',
        'RTI_ELIGIBILITY': 'Identify eligibility questions without assuming a verified entitlement.',
        'REQUEST_STRUCTURING': 'Structure required public information and request history.',
        'EXEMPTION_RISK': 'Identify facts requiring exemption-law retrieval, not assumed exemptions.',
        'RTI_APPEAL_FOUNDATION': 'Structure request/appeal procedural facts; no professional draft.',
    },
}
CATALOG = {name: {'domain': domain, 'purpose': purpose} for domain, pack in PACKS.items() for name, purpose in pack.items()}
CONDITIONAL = {'BOUNDARY_SURVEY', 'RENT_DEPOSIT', 'DIGITAL_EVIDENCE', 'MEDICAL_EVIDENCE', 'WITNESS'}
