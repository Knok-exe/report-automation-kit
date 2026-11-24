-- title: Medication safety: metformin without recent renal function test
-- question: Which patients on active metformin have no creatinine or eGFR result in the lookback window?
-- key: patient_id
-- requires: patients, medications, observations
-- param window_days: 365
-- limitations: Illustrative monitoring rule, not a clinical guideline. Creatinine LOINC 2160-0 and eGFR LOINC 62238-1 / 33914-3 count as renal function tests. Metformin = RxNorm 861007, 860975, 861004. A patient with the test recorded in another system will appear here. Synthetic data.
WITH on_metformin AS (
    SELECT patient AS patient_id, MIN(start) AS med_start, MIN(description) AS medication
    FROM medications
    WHERE code IN ('861007', '860975', '861004')
      AND start <= :as_of
      AND (stop IS NULL OR stop > :as_of)
    GROUP BY patient
),
last_test AS (
    SELECT patient, MAX(date) AS last_renal_test
    FROM observations
    WHERE code IN ('2160-0', '62238-1', '33914-3') AND date <= :as_of
    GROUP BY patient
)
SELECT m.patient_id,
       p."first" || ' ' || p."last" AS name,
       CAST((julianday(:as_of) - julianday(p.birthdate)) / 365.25 AS INTEGER) AS age,
       m.medication,
       m.med_start,
       t.last_renal_test,
       CAST(julianday(:as_of) - julianday(t.last_renal_test) AS INTEGER) AS days_since_test
FROM on_metformin m
JOIN patients p ON p.id = m.patient_id
LEFT JOIN last_test t ON t.patient = m.patient_id
WHERE t.last_renal_test IS NULL
   OR t.last_renal_test < date(:as_of, '-' || :window_days || ' days')
ORDER BY t.last_renal_test IS NOT NULL, days_since_test DESC, name, m.patient_id;
