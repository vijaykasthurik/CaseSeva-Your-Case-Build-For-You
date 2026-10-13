# Phase 4: independent admin-review checklist

Prepared 13 October 2026 (Asia/Calcutta). All 14 current revisions remain REVIEW_PENDING. These are assistant recommendations, not admin decisions. No authority, user account or review receipt was modified.

**Recommendation: NEEDS_NEW_REVISION for all 14.** An identity/hash/boundary PASS does not establish current law, applicability or adequate rule metadata. No APPROVE or REJECT decision is being made for you.

## How to review each record

1. Open the original PDF and compare the full stored excerpt below, including exceptions and qualifications. Extraction noise is retained verbatim here so it is visible for review.
2. Confirm the exact instrument, provision and version; identify later changes and evidence of applicable commencement.
3. Resolve each temporal, amendment, jurisdiction and structured-rule concern before approving a corrected revision. Source review and case-specific applicability are distinct decisions.
4. State your decision and rationale for one exact source_id/revision. Recommendations below do not preselect or record your decision.
5. Formal decisions require the authenticated admin workflow, which derives reviewer identity and time from the real account and server. Do not send passwords or access tokens in chat.

## Recording gaps to resolve before formal decisions

- The isolated validation database currently contains zero admin accounts. No account has been created or promoted. A real authenticated reviewer must be connected to this dataset.
- The API now supports the exact `NEEDS_NEW_REVISION` decision with persisted `REVISION_REQUESTED` status while keeping the source `REVIEW_PENDING` and unusable. [The workflow and record 1 draft](phase4-revision-request-workflow.md) document the change and safe authentication steps. No formal decision has been recorded because a real administrator is not yet connected.
- Chat answers can give review instructions, but are not themselves authenticated admin receipts. All actual decision/identity/timestamp fields in the companion JSON remain null.

## Overview

| # | source_id | Authority / provision | Revision (short) | Recommendation |
| --- | --- | --- | --- | --- |
| 1 | [cpa2019_s2_7](#cpa2019-s2-7) | Consumer Protection Act 2019; Section 2(7) | `d9804b732b3d` | NEEDS_NEW_REVISION |
| 2 | [cpa2019_s2_10](#cpa2019-s2-10) | Consumer Protection Act 2019; Section 2(10) | `b4f5079de892` | NEEDS_NEW_REVISION |
| 3 | [cpa2019_s2_11](#cpa2019-s2-11) | Consumer Protection Act 2019; Section 2(11) | `743151b79fbe` | NEEDS_NEW_REVISION |
| 4 | [cpa2019_s34](#cpa2019-s34) | Consumer Protection Act 2019; Section 34 | `3fdd07a059fa` | NEEDS_NEW_REVISION |
| 5 | [cpa2019_s39](#cpa2019-s39) | Consumer Protection Act 2019; Section 39 | `49f660e732b3` | NEEDS_NEW_REVISION |
| 6 | [cpa2019_s69](#cpa2019-s69) | Consumer Protection Act 2019; Section 69 | `bb561eb9f49c` | NEEDS_NEW_REVISION |
| 7 | [cpa_commencement_2351](#cpa-commencement-2351) | Commencement notification S.O. 2351(E); S.O. 2351(E), 15 July 2020 (stored section=null) | `7e2dcb4a26af` | NEEDS_NEW_REVISION |
| 8 | [cpa_jurisdiction2021_r1](#cpa-jurisdiction2021-r1) | Consumer jurisdiction rules 2021; Rule 1 | `8661f1a6256e` | NEEDS_NEW_REVISION |
| 9 | [cpa_jurisdiction2021_r3](#cpa-jurisdiction2021-r3) | Consumer jurisdiction rules 2021; Rule 3 | `2611c410fe4e` | NEEDS_NEW_REVISION |
| 10 | [rti2005_s1](#rti2005-s1) | RTI Act 2005; Section 1 | `2f32810c72eb` | NEEDS_NEW_REVISION |
| 11 | [rti2005_s3](#rti2005-s3) | RTI Act 2005; Section 3 | `adf39cc91611` | NEEDS_NEW_REVISION |
| 12 | [rti2005_s6](#rti2005-s6) | RTI Act 2005; Section 6 | `0bb19450f78d` | NEEDS_NEW_REVISION |
| 13 | [rti2005_s7](#rti2005-s7) | RTI Act 2005; Section 7 | `fa3b7e3fc4e0` | NEEDS_NEW_REVISION |
| 14 | [rti2005_s19](#rti2005-s19) | RTI Act 2005; Section 19 | `d4df79a75eaf` | NEEDS_NEW_REVISION |

## cpa2019_s2_7

Record 1 of 14.

| Review field | Current record / assessment |
| --- | --- |
| source_id | cpa2019_s2_7 |
| Authority title (stored) | THE CONSUMER PROTECTION ACT, 2019 |
| Section/rule | Section 2(7) |
| Official PDF | [Open original PDF](https://consumeraffairs.gov.in/public/upload/files/CP%20Act%202019_1732700731.pdf) |
| Current revision | `d9804b732b3d855c06cf5c0143b721a5e9d0ad775092810c2f236150a51a024e` |
| Identity check result | PASS — automated registered-host, text hash, title and stored boundary checks only; not independent legal review. |
| Amendment/version concern | Original 2019 enactment; no documented check of subsequent changes relevant to this provision or the 2026 case. Original text must not be presented as a verified current consolidation. |
| Effective-date concern | effective_from=2020-07-20 is a candidate from S.O. 2351(E); temporal_reviewed=false. Neither the dependency nor provision-specific date applicability is approved. |
| Temporal-support requirement | cpa_commencement_2351 — pending, not independently approved. |
| Structured-rule concern | Preserve the complete definition, exclusions and Explanation. Empty rules may be appropriate for a definition, but record that scope explicitly; consumer status is not automatically proved by purchase. |
| Recommended action | **NEEDS_NEW_REVISION** |
| Exact reason | Current-law coverage and provision-specific commencement support are unreviewed. Keep the complete exclusions/Explanation and establish reviewed temporal metadata before approval. |
| Actual admin decision | NOT RECORDED |
| Excerpt offsets | [5213, 6724) in stored original extracted text |

**Exact stored excerpt — unchanged, including layout artifacts:**

```text
(7) "consumer" means any person who—
(i) buys any goods for a consideration which has been paid or promised
or partly paid and partly promised, or under any system of deferred payment
and includes any user of such goods other than the person who buys such
goods for consideration paid or promised or partly paid or partly promised, or
under any system of deferred payment, when such use is made with the approval
of such person, but does not include a person who obtains such goods for
resale or for any commercial purpose; or
(ii) hires or avails of any service for a consideration which has been paid
or promised or partly paid and partly promised, or under any system of deferred
payment and includes any beneficiary of such service other than the person
who hires or avails of the services for consideration paid or promised, or partly
paid and partly promised, or under any system of deferred payment, when such
services are availed of with the approval of the first mentioned person, but does
not include a person who avails of such service for any commercial purpose.
Explanation.—For the purposes of this clause,—
(a) the expression "commercial purpose" does not include use by a
person of goods bought and used by him exclusively for the purpose of
earning his livelihood, by means of self-employment;
(b) the expressions "buys any goods" and "hires or avails any
services" includes offline or online transactions through electronic means
or by teleshopping or direct selling or multi-level marketing;

```

Decision prompts: Do you request a new revision addressing the listed concerns, reject this record with a reason, or provide source-backed corrections for further review? Approval is not recommended while these concerns remain unresolved.

## cpa2019_s2_10

Record 2 of 14.

| Review field | Current record / assessment |
| --- | --- |
| source_id | cpa2019_s2_10 |
| Authority title (stored) | THE CONSUMER PROTECTION ACT, 2019 |
| Section/rule | Section 2(10) |
| Official PDF | [Open original PDF](https://consumeraffairs.gov.in/public/upload/files/CP%20Act%202019_1732700731.pdf) |
| Current revision | `b4f5079de892801f5f05478fe708786f02b95611bb67b68dbbf1d63c438d9353` |
| Identity check result | PASS — automated registered-host, text hash, title and stored boundary checks only; not independent legal review. |
| Amendment/version concern | Original 2019 enactment; no documented check of subsequent changes relevant to this provision or the 2026 case. Original text must not be presented as a verified current consolidation. |
| Effective-date concern | effective_from=2020-07-20 is a candidate from S.O. 2351(E); temporal_reviewed=false. Neither the dependency nor provision-specific date applicability is approved. |
| Temporal-support requirement | cpa_commencement_2351 — pending, not independently approved. |
| Structured-rule concern | No structured rule recorded. Definition alone does not establish cause, timing or proof of a defect in the case. |
| Recommended action | **NEEDS_NEW_REVISION** |
| Exact reason | Unreviewed amendment coverage and commencement dependency; the unknown refrigerator defect cause must remain unknown. |
| Actual admin decision | NOT RECORDED |
| Excerpt offsets | [7723, 8116) in stored original extracted text |

**Exact stored excerpt — unchanged, including layout artifacts:**

```text
(10) "defect" means any fault, imperfection or shortcoming in the quality,
quantity, potency, purity or standard which is required to be maintained by or under
any law for the time being in force or under any contract, express or implied or as is
claimed by the trader in any manner whatsoever in relation to any goods or product
and the expression "defective" shall be construed accordingly;

```

Decision prompts: Do you request a new revision addressing the listed concerns, reject this record with a reason, or provide source-backed corrections for further review? Approval is not recommended while these concerns remain unresolved.

## cpa2019_s2_11

Record 3 of 14.

| Review field | Current record / assessment |
| --- | --- |
| source_id | cpa2019_s2_11 |
| Authority title (stored) | THE CONSUMER PROTECTION ACT, 2019 |
| Section/rule | Section 2(11) |
| Official PDF | [Open original PDF](https://consumeraffairs.gov.in/public/upload/files/CP%20Act%202019_1732700731.pdf) |
| Current revision | `743151b79fbeb11660c63b60530e3036db43ba8d9b25fdc3fae94f15b73205ee` |
| Identity check result | PASS — automated registered-host, text hash, title and stored boundary checks only; not independent legal review. |
| Amendment/version concern | Original 2019 enactment; no documented check of subsequent changes relevant to this provision or the 2026 case. Original text must not be presented as a verified current consolidation. |
| Effective-date concern | effective_from=2020-07-20 is a candidate from S.O. 2351(E); temporal_reviewed=false. Neither the dependency nor provision-specific date applicability is approved. |
| Temporal-support requirement | cpa_commencement_2351 — pending, not independently approved. |
| Structured-rule concern | No structured rule recorded. Do not turn a service-deficiency definition into a finding that any particular party breached an obligation. |
| Recommended action | **NEEDS_NEW_REVISION** |
| Exact reason | Unreviewed version and commencement support; applicability to goods versus alleged services must remain conditional. |
| Actual admin decision | NOT RECORDED |
| Excerpt offsets | [8116, 8655) in stored original extracted text |

**Exact stored excerpt — unchanged, including layout artifacts:**

```text
(11) "deficiency" means any fault, imperfection, shortcoming or inadequacy in
the quality, nature and manner of performance which is required to be maintained by or
under any law for the time being in force or has been undertaken to be performed by a
person in pursuance of a contract or otherwise in relation to any service and includes—
(i) any act of negligence or omission or commission by such person which
causes loss or injury to the consumer; and
(ii) deliberate withholding of relevant information by such person to the
consumer;

```

Decision prompts: Do you request a new revision addressing the listed concerns, reject this record with a reason, or provide source-backed corrections for further review? Approval is not recommended while these concerns remain unresolved.

## cpa2019_s34

Record 4 of 14.

| Review field | Current record / assessment |
| --- | --- |
| source_id | cpa2019_s34 |
| Authority title (stored) | THE CONSUMER PROTECTION ACT, 2019 |
| Section/rule | Section 34 |
| Official PDF | [Open original PDF](https://consumeraffairs.gov.in/public/upload/files/CP%20Act%202019_1732700731.pdf) |
| Current revision | `3fdd07a059fa3be18328738bb1146722110f96f19eb5fce579d7d8f0af6b8b66` |
| Identity check result | PASS — automated registered-host, text hash, title and stored boundary checks only; not independent legal review. |
| Amendment/version concern | Original 2019 enactment; no documented check of subsequent changes relevant to this provision or the 2026 case. Original text must not be presented as a verified current consolidation. |
| Effective-date concern | effective_from=2020-07-20 is a candidate from S.O. 2351(E); temporal_reviewed=false. Neither the dependency nor provision-specific date applicability is approved. |
| Temporal-support requirement | cpa_commencement_2351 — pending, not independently approved. |
| Structured-rule concern | rules={} cannot express the reviewed territorial/pecuniary interaction. The stored original excerpt includes one crore; link the later rule rather than treating this as the current threshold. Excerpt also contains unrelated marginal headings. |
| Recommended action | **NEEDS_NEW_REVISION** |
| Exact reason | Unresolved interaction with jurisdiction Rule 3, incomplete version/temporal treatment, and extraction noise. A clean, source-bound version is required; case forum facts need separate review. |
| Actual admin decision | NOT RECORDED |
| Excerpt offsets | [50119, 51897) in stored original extracted text |

**Exact stored excerpt — unchanged, including layout artifacts:**

```text
34. (1) Subject to the other provisions of this Act, the District Commission shall have
jurisdiction to entertain complaints where the value of the goods or services paid as
consideration does not exceed one crore rupees:
Provided that where the Central Government deems it necessary so to do, it may
prescribe such other value, as it deems fit.
(2) A complaint shall be instituted in a District Commission within the local limits of
whose jurisdiction,—
(a) the opposite party or each of the opposite parties, where there are more than
one, at the time of the institution of the complaint, ordinarily resides or carries on
business or has a branch office or personally works for gain; or
(b) any of the opposite parties, where there are more than one, at the time of the
institution of the complaint, actually and voluntarily resides, or carries on business or
has a branch office, or personally works for gain, provided that in such case the
permission of the District Commission is given; or
(c) the cause of action, wholly or in part, arises; or
(d) the complainant resides or personally works for gain.
Qualifications,
etc., of
President and
members of
District
Commission.
Salaries,
allowances and
other terms
and conditions
of service of
President and
members of
District
Commission.
Transitional
provision.
Vacancy in
office of
member of
District
Commission.
Officers and
other
employees of
District
Commission.
Jurisdiction of
District
Commission.

18
THE GAZETTE OF INDIA EXTRAORDINARY
[PART II—
(3) The District Commission shall ordinarily function in the district headquarters and
may perform its functions at such other place in the district, as the State Government may, in
consultation with the State Commission, notify in the Official Gazette from time to time.

```

Decision prompts: Do you request a new revision addressing the listed concerns, reject this record with a reason, or provide source-backed corrections for further review? Approval is not recommended while these concerns remain unresolved.

## cpa2019_s39

Record 5 of 14.

| Review field | Current record / assessment |
| --- | --- |
| source_id | cpa2019_s39 |
| Authority title (stored) | THE CONSUMER PROTECTION ACT, 2019 |
| Section/rule | Section 39 |
| Official PDF | [Open original PDF](https://consumeraffairs.gov.in/public/upload/files/CP%20Act%202019_1732700731.pdf) |
| Current revision | `49f660e732b3e1544838f6817d40964d2f15363099a6b1907c28c52db56db376` |
| Identity check result | PASS — automated registered-host, text hash, title and stored boundary checks only; not independent legal review. |
| Amendment/version concern | Original 2019 enactment; no documented check of subsequent changes relevant to this provision or the 2026 case. Original text must not be presented as a verified current consolidation. |
| Effective-date concern | effective_from=2020-07-20 is a candidate from S.O. 2351(E); temporal_reviewed=false. Neither the dependency nor provision-specific date applicability is approved. |
| Temporal-support requirement | cpa_commencement_2351 — pending, not independently approved. |
| Structured-rule concern | One broad remedies entry copies the entire section and uses consumer_status, defect_or_deficiency and relief_basis; rules_reviewed=false. Separate supported remedy conditions and preserve judicial discretion. Excerpt includes page/margin text. |
| Recommended action | **NEEDS_NEW_REVISION** |
| Exact reason | Unreviewed blanket remedy metadata, source version and commencement. The present rule is too broad to establish any particular remedy for this case. |
| Actual admin decision | NOT RECORDED |
| Excerpt offsets | [63395, 66688) in stored original extracted text |

**Exact stored excerpt — unchanged, including layout artifacts:**

```text
39. (1) Where the District Commission is satisfied that the goods complained against
suffer from any of the defects specified in the complaint or that any of the allegations
contained in the complaint about the services or any unfair trade practices, or claims for
compensation under product liability are proved, it shall issue an order to the opposite party
directing him to do one or more of the following, namely:—
(a) to remove the defect pointed out by the appropriate laboratory from the
goods in question;
(b) to replace the goods with new goods of similar description which shall be
free from any defect;
(c) to return to the complainant the price, or, as the case may be, the charges paid
by the complainant along with such interest on such price or charges as may be
decided;
(d) to pay such amount as may be awarded by it as compensation to the consumer
for any loss or injury suffered by the consumer due to the negligence of the opposite
party:
Provided that the District Commission shall have the power to grant punitive
damages in such circumstances as it deems fit;
(e) to pay such amount as may be awarded by it as compensation in a product
liability action under Chapter VI;
(f) to remove the defects in goods or deficiencies in the services in question;
(g) to discontinue the unfair trade practice or restrictive trade practice and not to
repeat them;
(h) not to offer the hazardous or unsafe goods for sale;
(i) to withdraw the hazardous goods from being offered for sale;
(j) to cease manufacture of hazardous goods and to desist from offering services
which are hazardous in nature;
(k) to pay such sum as may be determined by it, if it is of the opinion that loss or
injury has been suffered by a large number of consumers who are not identifiable
conveniently:
Provided that the minimum amount of sum so payable shall not be less than
twenty-five per cent. of the value of such defective goods sold or service provided, as
the case may be, to such consumers;
Findings of
District
Commission.
45 of 1860.
2 of 1974.
5 of 1908.
5 of 1908.

22
THE GAZETTE OF INDIA EXTRAORDINARY
[PART II—
(l) to issue corrective advertisement to neutralise the effect of misleading
advertisement at the cost of the opposite party responsible for issuing such misleading
advertisement;
(m) to provide for adequate costs to parties; and
(n) to cease and desist from issuing any misleading advertisement.
(2) Any amount obtained under sub-section (1) shall be credited to such fund and
utilised in such manner as may be prescribed.
(3) In any proceeding conducted by the President and a member and if they differ on
any point or points, they shall state the point or points on which they differ and refer the
same to another member for hearing on such point or points and the opinion of the majority
shall be the order of the District Commission:
Provided that the other member shall give his opinion on such point or points referred
to him within a period of one month from the date of such reference.
(4) Every order made by the District Commission under sub-section (1) shall be signed
by the President and the member who conducted the proceeding:
Provided that where the order is made as per majority opinion under sub-section (3),
such order shall also be signed by the other member.

```

Decision prompts: Do you request a new revision addressing the listed concerns, reject this record with a reason, or provide source-backed corrections for further review? Approval is not recommended while these concerns remain unresolved.

## cpa2019_s69

Record 6 of 14.

| Review field | Current record / assessment |
| --- | --- |
| source_id | cpa2019_s69 |
| Authority title (stored) | THE CONSUMER PROTECTION ACT, 2019 |
| Section/rule | Section 69 |
| Official PDF | [Open original PDF](https://consumeraffairs.gov.in/public/upload/files/CP%20Act%202019_1732700731.pdf) |
| Current revision | `bb561eb9f49cf25ba314deb8bd15243293fdc619950105646c135aac3003776c` |
| Identity check result | PASS — automated registered-host, text hash, title and stored boundary checks only; not independent legal review. |
| Amendment/version concern | Original 2019 enactment; no documented check of subsequent changes relevant to this provision or the 2026 case. Original text must not be presented as a verified current consolidation. |
| Effective-date concern | effective_from=2020-07-20 is a candidate from S.O. 2351(E); temporal_reviewed=false. Neither the dependency nor provision-specific date applicability is approved. |
| Temporal-support requirement | cpa_commencement_2351 — pending, not independently approved. |
| Structured-rule concern | Draft limitation stores years=2; rules_reviewed=false. Cause-of-action trigger and condonation are not a purchase-date formula. Exact trigger, exclusions and any applicable extensions need supported case-specific review. |
| Recommended action | **NEEDS_NEW_REVISION** |
| Exact reason | Duration metadata is not independently reviewed and does not settle trigger/condonation. Version and temporal support are pending; no automatic deadline is permissible. |
| Actual admin decision | NOT RECORDED |
| Excerpt offsets | [88515, 89255) in stored original extracted text |

**Exact stored excerpt — unchanged, including layout artifacts:**

```text
69. (1) The District Commission, the State Commission or the National Commission
shall not admit a complaint unless it is filed within two years from the date on which the
cause of action has arisen.
(2) Notwithstanding anything contained in sub-section (1), a complaint may be
entertained after the period specified in sub-section (1), if the complainant satisfies the
District Commission, the State Commission or the National Commission, as the case may be,
that he had sufficient cause for not filing the complaint within such period:
Provided that no such complaint shall be entertained unless the District Commission
or the State Commission or the National Commission, as the case may be, records its reasons
for condoning such delay.

```

Decision prompts: Do you request a new revision addressing the listed concerns, reject this record with a reason, or provide source-backed corrections for further review? Approval is not recommended while these concerns remain unresolved.

## cpa_commencement_2351

Record 7 of 14.

| Review field | Current record / assessment |
| --- | --- |
| source_id | cpa_commencement_2351 |
| Authority title (stored) | MINISTRY OF CONSUMER AFFAIRS, FOOD AND PUBLIC DISTRIBUTION |
| Section/rule | S.O. 2351(E), 15 July 2020 (stored section=null) |
| Official PDF | [Open original PDF](https://consumeraffairs.gov.in/public/upload/files/Act%20into%20force_1732702865.pdf) |
| Current revision | `7e2dcb4a26af77e48790839bd6df946687b7668d2a3f58125f2c7a9ce02aa370` |
| Identity check result | PASS — automated registered-host, text hash, title and stored boundary checks only; not independent legal review. |
| Amendment/version concern | No documented check for later changes affecting this instrument or its supported provisions. |
| Effective-date concern | effective_from=2020-07-20 is grounded in the downloaded notification but temporal_reviewed=false; confirm its exact provision/exclusion scope. |
| Temporal-support requirement | cpa_commencement_2351 — pending, not independently approved. Verify this source itself against the exact notification and record the reviewed scope. |
| Structured-rule concern | rules={} contains no explicit provision/exclusion mapping. Stored title/citation identifies the Ministry generically rather than the notification number/date; excerpt includes unrelated trailing extraction/signature text. |
| Recommended action | **NEEDS_NEW_REVISION** |
| Exact reason | Needs precise notification identity/scope and reviewed provision-specific commencement mapping. A self-reference is not an independent confirmation, and temporal_reviewed is false. |
| Actual admin decision | NOT RECORDED |
| Excerpt offsets | [1346, 2922) in stored original extracted text |

**Exact stored excerpt — unchanged, including layout artifacts:**

```text
MINISTRY OF CONSUMER AFFAIRS, FOOD AND PUBLIC DISTRIBUTION 
(Department of Consumer Affairs) 
NOTIFICATION 
New Delhi, the 15th July, 2020 
S.O. 2351(E).—In exercise of the powers conferred by sub-section (3) of section 1 of the Consumer 
Protection Act, 2019 (35 of 2019), the Central Government hereby appoints the 20th day of July, 2020 as the date on 
which the following provisions of the said Act shall come into force, namely:- 
Chapter 
Sections 
I 
Section 2  
[Except clauses (4), (13), (14), (16), (40)] 
II 
Sections 3 to 9 (both inclusive); 
IV 
Sections 28 to 73 (both inclusive); 
[Except sub-clause (iv) of clause (a) of sub-section (1) of section 58.] 
V 
Sections 74 to 81 (both inclusive); 
VI 
Sections 82 to 87 (both inclusive); 
VII 
Sections 90 and  91; 
[Except sections 88,89,92 & 93] 
VIII 
-Sections 95, 98, 100,  
-Section101  
[Except clauses (f) to (m) and clauses (zg), (zh) and (zi) of sub –section 2 ].   
-Sections 102, 103, 105, 106, 107 
 
[ Except sections 94, 96,97,99, 104] 
 
[F. No. J-9/1/2020-CPU] 
AMIT MEHTA, Jt. Secy. 
 
 
 
 
 
 
 
 
 
Uploaded by Dte. of Printing at Government of India Press, Ring Road, Mayapuri, New Delhi-110064 
and Published by the Controller of Publications, Delhi-110054. 
VIII 
-धारा 95, धारा 98, धारा 100,  
-धारा 101  
[उप-धारा 2 के खंड (च) से (ड) तथा खंड (यछ), (यज) और (यझ) के जसर्ाय]    
-धारा 102,  धारा 103,  धारा 105,  धारा 106,  धारा 107 
[ धारा 94,  धारा 96,  धारा 97,  धारा 99,  धारा 104 के जसर्ाय] 
MANOJ KUMAR 
VERMA
Digitally signed by 
MANOJ KUMAR VERMA 
Date: 2020.07.16 
16:14:34 +05'30'

```

Decision prompts: Do you request a new revision addressing the listed concerns, reject this record with a reason, or provide source-backed corrections for further review? Approval is not recommended while these concerns remain unresolved.

## cpa_jurisdiction2021_r1

Record 8 of 14.

| Review field | Current record / assessment |
| --- | --- |
| source_id | cpa_jurisdiction2021_r1 |
| Authority title (stored) | Consumer Protection (Jurisdiction of the District Commission, the State Commission and the National Commission) Rules, 2021 |
| Section/rule | Rule 1 |
| Official PDF | [Open original PDF](https://consumeraffairs.gov.in/public/upload/files/232278_1732705029.pdf) |
| Current revision | `8661f1a6256e67794a4c3700a1fd059d6a65e4da51585305bcbfce37ad8fa4fa` |
| Identity check result | PASS — automated registered-host, text hash, title and stored boundary checks only; not independent legal review. |
| Amendment/version concern | No documented check for later changes affecting this instrument or its supported provisions. |
| Effective-date concern | effective_from is null. The record flags 30 December 2021 in the notification/header and 31 December in upload/signature metadata. Establish legally relevant publication evidence; do not equate upload date with commencement. |
| Temporal-support requirement | cpa_jurisdiction2021_r1 — pending, not independently approved. |
| Structured-rule concern | No operative computation recorded; correct citation label from section to rule. Publication date must be distinguished from upload/signature date. |
| Recommended action | **NEEDS_NEW_REVISION** |
| Exact reason | Effective date is absent; temporal support currently points to itself. Resolve publication evidence and version applicability before marking any dependent jurisdiction rule usable. |
| Actual admin decision | NOT RECORDED |
| Excerpt offsets | [3080, 3370) in stored original extracted text |

**Exact stored excerpt — unchanged, including layout artifacts:**

```text
1.       Short title and commencement.—(1) These rules may be called the Consumer Protection (Jurisdiction of the 
District Commission, the State Commission and the National Commission) Rules, 2021. 
(2) They shall come into force on the date of their publication in the official gazette. 

```

Decision prompts: Do you request a new revision addressing the listed concerns, reject this record with a reason, or provide source-backed corrections for further review? Approval is not recommended while these concerns remain unresolved.

## cpa_jurisdiction2021_r3

Record 9 of 14.

| Review field | Current record / assessment |
| --- | --- |
| source_id | cpa_jurisdiction2021_r3 |
| Authority title (stored) | Consumer Protection (Jurisdiction of the District Commission, the State Commission and the National Commission) Rules, 2021 |
| Section/rule | Rule 3 |
| Official PDF | [Open original PDF](https://consumeraffairs.gov.in/public/upload/files/232278_1732705029.pdf) |
| Current revision | `2611c410fe4e48a978a000d2419e5ac391675ce8bb8db07d82804c8619df1ec0` |
| Identity check result | PASS — automated registered-host, text hash, title and stored boundary checks only; not independent legal review. |
| Amendment/version concern | No documented check for later changes affecting this instrument or its supported provisions. |
| Effective-date concern | effective_from is null. The record flags 30 December 2021 in the notification/header and 31 December in upload/signature metadata. Establish legally relevant publication evidence; do not equate upload date with commencement. |
| Temporal-support requirement | cpa_jurisdiction2021_r1 — pending, not independently approved. |
| Structured-rule concern | Draft forum rule requires consideration_paid, territorial_basis and consumer_status; rules_reviewed=false. Bind its amount test to verified facts and separately supported territorial basis. Correct citation label from section to rule. |
| Recommended action | **NEEDS_NEW_REVISION** |
| Exact reason | Unresolved commencement and Rule 1 dependency, unreviewed structured forum metadata and incomplete case-specific jurisdiction facts. |
| Actual admin decision | NOT RECORDED |
| Excerpt offsets | [3795, 4130) in stored original extracted text |

**Exact stored excerpt — unchanged, including layout artifacts:**

```text
3.       Jurisdiction of District Commission.—Subject to the other provisions of the Act and in pursuance of proviso 
to sub-section (1) of section 34 of the Act, the District Commission shall have jurisdiction to entertain complaints 
where the value of the goods or services paid as consideration does not exceed fifty lakh rupees. 

```

Decision prompts: Do you request a new revision addressing the listed concerns, reject this record with a reason, or provide source-backed corrections for further review? Approval is not recommended while these concerns remain unresolved.

## rti2005_s1

Record 10 of 14.

| Review field | Current record / assessment |
| --- | --- |
| source_id | rti2005_s1 |
| Authority title (stored) | THE RIGHT TO INFORMATION ACT, 2005 |
| Section/rule | Section 1 |
| Official PDF | [Open original PDF](https://cic.gov.in/sites/default/files/RTI_English.pdf) |
| Current revision | `2f32810c72ebceffcfffb61133f7b848dd83f1ec1ba9d2dd297b3b9a4a2a95a3` |
| Identity check result | PASS — automated registered-host, text hash, title and stored boundary checks only; not independent legal review. |
| Amendment/version concern | Compilation marked as on 18 November 2025. Provision-specific amendment history and applicability to the actual event date have not been reviewed. |
| Effective-date concern | effective_from is null; temporal_reviewed=false. Review the section 1(3) commencement scheme and applicable territorial/amendment version; do not infer an event date. |
| Temporal-support requirement | rti2005_s1 — pending, not independently approved. Needs enacted/commencement and relevant amendment evidence, not merely a self-reference. |
| Structured-rule concern | rules={} has no provision-specific commencement mapping. The excerpt contains the amendment marker 1*** without the linked footnote in its quote; retain linked amendment support. |
| Recommended action | **NEEDS_NEW_REVISION** |
| Exact reason | Missing effective date and independently reviewed commencement mapping; territorial amendment/version context is incomplete in the excerpt. |
| Actual admin decision | NOT RECORDED |
| Excerpt offsets | [3988, 4419) in stored original extracted text |

**Exact stored excerpt — unchanged, including layout artifacts:**

```text
1. Short title, extent and commencement.—(1) This Act may be called the Right to Information 
Act, 2005. 
(2) It extends to the whole of India 1***. 
(3) The provisions of sub-section (1) of section 4, sub-sections (1) and (2) of section 5, sections 12, 
13, 15,16, 24, 27 and 28 shall come into force at once, and the remaining provisions of this Act shall 
come into force on the one hundred and twentieth day of its enactment. 

```

Decision prompts: Do you request a new revision addressing the listed concerns, reject this record with a reason, or provide source-backed corrections for further review? Approval is not recommended while these concerns remain unresolved.

## rti2005_s3

Record 11 of 14.

| Review field | Current record / assessment |
| --- | --- |
| source_id | rti2005_s3 |
| Authority title (stored) | THE RIGHT TO INFORMATION ACT, 2005 |
| Section/rule | Section 3 |
| Official PDF | [Open original PDF](https://cic.gov.in/sites/default/files/RTI_English.pdf) |
| Current revision | `adf39cc91611345ea1816724f4aedd552e8626810724fc19fb8f5c5af41a0459` |
| Identity check result | PASS — automated registered-host, text hash, title and stored boundary checks only; not independent legal review. |
| Amendment/version concern | Compilation marked as on 18 November 2025. Provision-specific amendment history and applicability to the actual event date have not been reviewed. |
| Effective-date concern | effective_from is null; temporal_reviewed=false. Review the section 1(3) commencement scheme and applicable territorial/amendment version; do not infer an event date. |
| Temporal-support requirement | rti2005_s1 — pending, not independently approved. |
| Structured-rule concern | No structured entitlement rule recorded. Preserve the subject-to-the-Act qualification; citizenship and public-authority applicability are separate facts, not assumptions. |
| Recommended action | **NEEDS_NEW_REVISION** |
| Exact reason | Missing reviewed effective/version metadata and pending section 1 support. The case has no verified location or event date. |
| Actual admin decision | NOT RECORDED |
| Excerpt offsets | [8824, 8940) in stored original extracted text |

**Exact stored excerpt — unchanged, including layout artifacts:**

```text
3. Right to information.—Subject to the provisions of this Act, all citizens shall have the right to 
information. 

```

Decision prompts: Do you request a new revision addressing the listed concerns, reject this record with a reason, or provide source-backed corrections for further review? Approval is not recommended while these concerns remain unresolved.

## rti2005_s6

Record 12 of 14.

| Review field | Current record / assessment |
| --- | --- |
| source_id | rti2005_s6 |
| Authority title (stored) | THE RIGHT TO INFORMATION ACT, 2005 |
| Section/rule | Section 6 |
| Official PDF | [Open original PDF](https://cic.gov.in/sites/default/files/RTI_English.pdf) |
| Current revision | `0bb19450f78d211276b45da19301510fc1af33ab1204ba510e9c88293c78d5b5` |
| Identity check result | PASS — automated registered-host, text hash, title and stored boundary checks only; not independent legal review. |
| Amendment/version concern | Compilation marked as on 18 November 2025. Provision-specific amendment history and applicability to the actual event date have not been reviewed. |
| Effective-date concern | effective_from is null; temporal_reviewed=false. Review the section 1(3) commencement scheme and applicable territorial/amendment version; do not infer an event date. |
| Temporal-support requirement | rti2005_s1 — pending, not independently approved. |
| Structured-rule concern | No reviewed request/fee/transfer rule. Required fee/procedure depends on the appropriate authority; do not infer the authority or location from a generic government-office description. |
| Recommended action | **NEEDS_NEW_REVISION** |
| Exact reason | Commencement and version review are pending; authority-specific procedural applicability is unresolved. |
| Actual admin decision | NOT RECORDED |
| Excerpt offsets | [15496, 17284) in stored original extracted text |

**Exact stored excerpt — unchanged, including layout artifacts:**

```text
 
6. Request for obtaining information.—(1) A person, who desires to obtain any information under 
this Act, shall make a request in writing or through electronic means in English or Hindi or in the official 
language of the area in which the application is being made, accompanying such fee as may be 
prescribed, to— 
(a) the Central Public Information Officer or State Public Information Officer, as the case may 
be, of the concerned public authority; 
(b) the Central Assistant Public Information Officer or State Assistant Public Information Officer, 
as the case may be, 
specifying the particulars of the information sought by him or her: 
Provided that where such request cannot be made in writing, the Central Public Information Officer 
or State Public Information Officer, as the case may be, shall render all reasonable assistance to the 
person making the request orally to reduce the same in writing. 
(2) An applicant making request for information shall not be required to give any reason for 
requesting the information or any other personal details except those that may be necessary for contacting 
him. 
(3) Where an application is made to a public authority requesting for an information,— 
(i) which is held by another public authority; or 
(ii) the subject matter of which is more closely connected with the functions of another public 
authority, 
the public authority, to which such application is made, shall transfer the application or such part of it as 
may be appropriate to that other public authority and inform the applicant immediately about such 
transfer: 
Provided that the transfer of an application pursuant to this sub-section shall be made as soon as 
practicable but in no case later than five days from the date of receipt of the application. 

```

Decision prompts: Do you request a new revision addressing the listed concerns, reject this record with a reason, or provide source-backed corrections for further review? Approval is not recommended while these concerns remain unresolved.

## rti2005_s7

Record 13 of 14.

| Review field | Current record / assessment |
| --- | --- |
| source_id | rti2005_s7 |
| Authority title (stored) | THE RIGHT TO INFORMATION ACT, 2005 |
| Section/rule | Section 7 |
| Official PDF | [Open original PDF](https://cic.gov.in/sites/default/files/RTI_English.pdf) |
| Current revision | `fa3b7e3fc4e0eb98241ed324cee75c4de596d3d572909566365dc1c1da89bfea` |
| Identity check result | PASS — automated registered-host, text hash, title and stored boundary checks only; not independent legal review. |
| Amendment/version concern | Compilation marked as on 18 November 2025. Provision-specific amendment history and applicability to the actual event date have not been reviewed. |
| Effective-date concern | effective_from is null; temporal_reviewed=false. Review the section 1(3) commencement scheme and applicable territorial/amendment version; do not infer an event date. |
| Temporal-support requirement | rti2005_s1 — pending, not independently approved. |
| Structured-rule concern | No reviewed deadline rule. Preserve alternatives, fee-intimation exclusions and referenced provisions; supporting sections 5, 8, 9 and 11 are not in this narrow reviewed bundle. Receipt/transfer/fee dates are unknown. |
| Recommended action | **NEEDS_NEW_REVISION** |
| Exact reason | Missing effective/version metadata and timing/exception dependencies. No generic response deadline can be computed for the existing undated fixture. |
| Actual admin decision | NOT RECORDED |
| Excerpt offsets | [17284, 21343) in stored original extracted text |

**Exact stored excerpt — unchanged, including layout artifacts:**

```text
7. Disposal of request.—(1) Subject to the proviso to sub-section (2) of section 5 or the proviso to 
sub-section (3) of section 6, the Central Public Information Officer or State Public Information Officer, as 
the case may be, on receipt of a request under section 6 shall, as expeditiously as possible, and in any case 
within thirty days of the receipt of the request, either provide the information on payment of such fee as 
may be prescribed or reject the request for any of the reasons specified in sections 8 and 9: 
Provided that where the information sought for concerns the life or liberty of a person, the same shall 
be provided within forty-eight hours of the receipt of the request. 
(2) If the Central Public Information Officer or State Public Information Officer, as the case may be, 
fails to give decision on the request for information within the period specified under sub-section (1), the 
Central Public Information Officer or State Public Information Officer, as the case may be, shall be 
deemed to have refused the request. 
(3) Where a decision is taken to provide the information on payment of any further fee representing 
the cost of providing the information, the Central Public Information Officer or State Public Information 
Officer, as the case may be, shall send an intimation to the person making the request, giving— 
(a) the details of further fees representing the cost of providing the information as determined by 
him, together with the calculations made to arrive at the amount in accordance with fee prescribed 
under sub-section (1), requesting him to deposit that fees, and the period intervening between the 
despatch of the said intimation and payment of fees shall be excluded for the purpose of calculating 
the period of thirty days referred to in that sub-section; 
(b) information concerning his or her right with respect to review the decision as to the amount of 
fees charged or the form of access provided, including the particulars of the appellate authority, time 
limit, process and any other forms. 

10 
 
(4) Where access to the record or a part thereof is required to be provided under this Act and the 
person to whom access is to be provided is sensorily disabled, the Central Public Information Officer or 
State Public Information Officer, as the case may be, shall provide assistance to enable access to the 
information, including providing such assistance as may be appropriate for the inspection. 
(5) Where access to information is to be provided in the printed or in any electronic format, the 
applicant shall, subject to the provisions of sub-section (6), pay such fee as may be prescribed: 
Provided that the fee prescribed under sub-section (1) of section 6 and sub-sections (1) and (5) of 
section 7 shall be reasonable and no such fee shall be charged from the persons who are of below poverty 
line as may be determined by the appropriate Government. 
(6) Notwithstanding anything contained in sub-section (5), the person making request for the 
information shall be provided the information free of charge where a public authority fails to comply with 
the time limits specified in sub-section (1). 
(7) Before taking any decision under sub-section (1), the Central Public Information Officer or State 
Public Information Officer, as the case may be, shall take into consideration the representation made by a 
third party under section 11. 
(8) Where a request has been rejected under sub-section (1), the Central Public Information Officer or 
State Public Information Officer, as the case may be, shall communicate to the person making the 
request,— 
(i) the reasons for such rejection; 
(ii) the period within which an appeal against such rejection may be preferred; and 
(iii) the particulars of the appellate authority. 
(9) An information shall ordinarily be provided in the form in which it is sought unless it would 
disproportionately divert the resources of the public authority or would be detrimental to the safety or 
preservation of the record in question. 

```

Decision prompts: Do you request a new revision addressing the listed concerns, reject this record with a reason, or provide source-backed corrections for further review? Approval is not recommended while these concerns remain unresolved.

## rti2005_s19

Record 14 of 14.

| Review field | Current record / assessment |
| --- | --- |
| source_id | rti2005_s19 |
| Authority title (stored) | THE RIGHT TO INFORMATION ACT, 2005 |
| Section/rule | Section 19 |
| Official PDF | [Open original PDF](https://cic.gov.in/sites/default/files/RTI_English.pdf) |
| Current revision | `d4df79a75eaf673547e75adf188aad807434fd8adf62e963f610012bf4dc5bae` |
| Identity check result | PASS — automated registered-host, text hash, title and stored boundary checks only; not independent legal review. |
| Amendment/version concern | Compilation marked as on 18 November 2025. Provision-specific amendment history and applicability to the actual event date have not been reviewed. |
| Effective-date concern | effective_from is null; temporal_reviewed=false. Review the section 1(3) commencement scheme and applicable territorial/amendment version; do not infer an event date. |
| Temporal-support requirement | rti2005_s1 — pending, not independently approved. |
| Structured-rule concern | No reviewed appeal/forum rule. Distinguish first/second appeal, triggers, condonation and the correct Information Commission; order, receipt and expiry facts are absent. |
| Recommended action | **NEEDS_NEW_REVISION** |
| Exact reason | Commencement/version and appeal-rule metadata are unresolved; the existing case cannot support a computed appeal deadline or selected appellate forum. |
| Actual admin decision | NOT RECORDED |
| Excerpt offsets | [47610, 51671) in stored original extracted text |

**Exact stored excerpt — unchanged, including layout artifacts:**

```text
19. Appeal.—(1) Any person who, does not receive a decision within the time specified in  
sub-section (1) or clause (a) of sub-section (3) of section 7, or is aggrieved by a decision of the Central 
Public Information Officer or State Public Information Officer, as the case may be, may within thirty days 
from the expiry of such period or from the receipt of such a decision prefer an appeal to such officer who 
is senior in rank to the Central Public Information Officer or State Public Information Officer as the case 
may be, in each public authority: 
Provided that such officer may admit the appeal after the expiry of the period of thirty days if he or 
she is satisfied that the appellant was prevented by sufficient cause from filing the appeal in time. 
(2) Where an appeal is preferred against an order made by a Central Public Information Officer or a 
State Public Information Officer, as the case may be, under section 11 to disclose third party information, 
the appeal by the concerned third party shall be made within thirty days from the date of the order. 

18 
 
(3) A second appeal against the decision under sub-section (1) shall lie within ninety days from the 
date on which the decision should have been made or was actually received, with the Central Information 
Commission or the State Information Commission: 
Provided that the Central Information Commission or the State Information Commission, as the case 
may be, may admit the appeal after the expiry of the period of ninety days if it is satisfied that the 
appellant was prevented by sufficient cause from filing the appeal in time. 
(4) If the decision of the Central Public Information Officer or State Public Information Officer, as 
the case may be, against which an appeal is preferred relates to information of a third party, the Central 
Information Commission or State Information Commission, as the case may be, shall give a reasonable 
opportunity of being heard to that third party. 
(5) In any appeal proceedings, the onus to prove that a denial of a request was justified shall be on the 
Central Public Information Officer or State Public Information Officer, as the case may be, who denied 
the request. 
(6) An appeal under sub-section (1) or sub-section (2) shall be disposed of within thirty days of the 
receipt of the appeal or within such extended period not exceeding a total of forty-five days from the date 
of filing thereof, as the case may be, for reasons to be recorded in writing. 
(7) The decision of the Central Information Commission or State Information Commission, as the 
case may be, shall be binding. 
(8) In its decision, the Central Information Commission or State Information Commission, as the case 
may be, has the power to— 
(a) require the public authority to take any such steps as may be necessary to secure compliance 
with the provisions of this Act, including— 
(i) by providing access to information, if so requested, in a particular form; 
(ii) by appointing a Central Public Information Officer or State Public Information Officer, as 
the case may be; 
(iii) by publishing certain information or categories of information; 
(iv) by making necessary changes to its practices in relation to the maintenance, management 
and destruction of records; 
(v) by enhancing the provision of training on the right to information for its officials; 
(vi) by providing it with an annual report in compliance with clause (b) of sub-section (1) of 
section 4; 
(b) require the public authority to compensate the complainant for any loss or other detriment 
suffered; 
(c) impose any of the penalties provided under this Act; 
(d) reject the application. 
(9) The Central Information Commission or State Information Commission, as the case may be, shall 
give notice of its decision, including any right of appeal, to the complainant and the public authority. 
(10) The Central Information Commission or State Information Commission, as the case may be, 
shall decide the appeal in accordance with such procedure as may be prescribed. 

```

Decision prompts: Do you request a new revision addressing the listed concerns, reject this record with a reason, or provide source-backed corrections for further review? Approval is not recommended while these concerns remain unresolved.
