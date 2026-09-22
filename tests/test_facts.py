import unittest

from landradar import SourceRef, Fact, ParcelRecord, audit_record


class FactsOnlyTests(unittest.TestCase):
    def test_fact_requires_source(self):
        record = ParcelRecord(cadastral_number='40:00:000000:1')
        with self.assertRaises(ValueError):
            record.add_fact(Fact(field='area_sqm', value=1200, source_ids=[]))

    def test_fact_rejects_unknown_source(self):
        record = ParcelRecord(cadastral_number='40:00:000000:1')
        with self.assertRaises(ValueError):
            record.add_fact(Fact(field='area_sqm', value=1200, source_ids=['missing']))

    def test_audit_reports_missing_without_scoring(self):
        record = ParcelRecord(cadastral_number='40:00:000000:1')
        record.add_source(SourceRef(source_id='s1', name='Official document', source_type='official_document'))
        record.add_fact(Fact(field='area_sqm', value=1200, unit='m2', source_ids=['s1']))
        result = audit_record(record, ['area_sqm', 'permitted_use'])
        self.assertEqual(result.fact_count, 1)
        self.assertEqual(result.missing_required_fields, ['permitted_use'])
        self.assertFalse(hasattr(result, 'landscore'))

    def test_conflict_is_explicit(self):
        record = ParcelRecord(cadastral_number='40:00:000000:1')
        record.add_source(SourceRef(source_id='s1', name='Source A', source_type='official_document'))
        record.add_source(SourceRef(source_id='s2', name='Source B', source_type='official_document'))
        record.add_fact(Fact(
            field='permitted_use',
            value=['value A', 'value B'],
            source_ids=['s1', 's2'],
            status='conflict',
        ))
        result = audit_record(record, ['permitted_use'])
        self.assertEqual(result.conflict_fields, ['permitted_use'])


if __name__ == '__main__':
    unittest.main()
