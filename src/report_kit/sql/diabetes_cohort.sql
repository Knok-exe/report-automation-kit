-- title: Diabetes cohort: HbA1c control
-- question: Among patients with active diabetes, who has a recent HbA1c and is it in control?
-- key: patient_id
-- summary: control_status
-- diff_ignore: age
-- requires: patients, conditions, observations
-- param window_days: 365
-- limitations: Illustrative thresholds (<7 in control, 7 to <9 above goal, >=9 poor), not individualised targets. Uses only the most recent HbA1c on or before the report date. Diabetes = SNOMED 44054006, 46635009 or 73211009 with no end date. Synthetic data.
WITH diabetics AS (
    SELECT DISTINCT patient AS patient_id
    FROM conditions
    WHERE code IN ('44054006', '46635009', '73211009')
      AND start <= :as_of
      AND (stop IS NULL OR stop > :as_of)
),
ranked AS (
    SELECT patient, date AS a1c_date, CAST(value AS REAL) AS a1c_value,
           ROW_NUMBER() OVER (PARTITION BY patient ORDER BY date DESC) AS rn
    FROM observations
    WHERE code = '4548-4' AND date <= :as_of AND value IS NOT NULL
)
SELECT d.patient_id,
       p."first" || ' ' || p."last" AS name,
       (CAST(strftime('%Y', :as_of) AS INTEGER) - CAST(strftime('%Y', p.birthdate) AS INTEGER)
        - (strftime('%m-%d', :as_of) < strftime('%m-%d', p.birthdate))) AS age,
       r.a1c_date,
       r.a1c_value,
       CASE
           WHEN r.a1c_date IS NULL OR r.a1c_date < date(:as_of, '-' || :window_days || ' days')
               THEN 'No recent test'
           WHEN r.a1c_value < 7 THEN 'In control (<7)'
           WHEN r.a1c_value < 9 THEN 'Above goal (7 to <9)'
           ELSE 'Poor control (>=9)'
       END AS control_status
FROM diabetics d
JOIN patients p ON p.id = d.patient_id
LEFT JOIN ranked r ON r.patient = d.patient_id AND r.rn = 1
ORDER BY control_status, name, d.patient_id;
