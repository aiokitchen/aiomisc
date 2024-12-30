from collections import defaultdict
from typing import DefaultDict, Iterable, Sequence, Set, Tuple

from .records import DNSRecord, RecordType


RecordsType = DefaultDict[Tuple[str, RecordType], Set[DNSRecord]]


class DNSZone:
    records: RecordsType
    name: str

    __slots__ = ("name", "records")

    def __init__(self, name: str, *records: DNSRecord) -> None:
        if not name.endswith("."):
            name += "."
        self.name = name
        self.records = defaultdict(set)

        for record in records:
            self.add_record(record)

    def add_record(self, record: DNSRecord) -> None:
        if not self.check_record(record):
            raise ValueError(
                f"Record {record.name} does not belong to zone {self.name}",
            )
        self.records[(record.name, record.type)].add(record)

    def remove_record(self, record: DNSRecord) -> None:
        key = (record.name, record.type)
        if key in self.records:
            self.records[key].discard(record)
            if self.records[key]:
                return
            del self.records[key]

    def get_records(
        self, name: str, record_type: RecordType,
    ) -> Sequence[DNSRecord]:
        if not name.endswith("."):
            name += "."
        return tuple(self.records.get((name, record_type), ()))

    def check_record(self, record: DNSRecord) -> bool:
        return record.name.endswith(self.name)

    def replace(self, records: Iterable[DNSRecord]) -> None:
        """
        Atomically replace all records in specified zone with new ones.
        This method is safe because it replaces all records at once.

        If any of the records does not belong to the zone, ValueError
        will be raised and no records will be replaced.
        """
        new_records: RecordsType = defaultdict(set)

        for record in records:
            if not self.check_record(record):
                raise ValueError(
                    f"Record {record.name} does not "
                    f"belong to zone {self.name}",
                )
            new_records[(record.name, record.type)].add(record)
        self.records = new_records
