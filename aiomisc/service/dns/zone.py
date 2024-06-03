from collections import defaultdict
from typing import DefaultDict, Sequence, Set, Tuple

from .records import DNSRecord, RecordType


class DNSZone:
    records: DefaultDict[Tuple[str, RecordType], Set[DNSRecord]]
    name: str

    __slots__ = ("name", "records")

    def __init__(self, name: str):
        if not name.endswith("."):
            name += "."
        self.name = name
        self.records = defaultdict(set)

    def add_record(self, record: DNSRecord) -> None:
        if not self._is_valid_record(record):
            raise ValueError(
                f"Record {record.name} does not belong to zone {self.name}",
            )
        key = (record.name, record.type)
        self.records[key].add(record)

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
        key = (name, record_type)
        return tuple(self.records.get(key, ()))

    def _is_valid_record(self, record: DNSRecord) -> bool:
        return record.name.endswith(self.name)
