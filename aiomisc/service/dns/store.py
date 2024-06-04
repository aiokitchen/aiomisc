from typing import Optional, Sequence, Tuple

from .records import DNSRecord, RecordType
from .tree import RadixTree
from .zone import DNSZone


class DNSStore:
    zones: RadixTree[DNSZone]

    __slots__ = ("zones",)

    def __init__(self) -> None:
        self.zones = RadixTree()

    def add_zone(self, zone: DNSZone) -> None:
        zone_tuple = self.get_reverse_tuple(zone.name)
        if self.zones.search(zone_tuple):
            raise ValueError(f"Zone {zone.name} already exists.")
        self.zones.insert(zone_tuple, zone)

    def remove_zone(self, zone_name: str) -> None:
        zone_tuple = self.get_reverse_tuple(zone_name)
        if not self.zones.search(zone_tuple):
            raise ValueError(
                f"Zone {zone_name} does not exist.",
            )
        # Clear zone from RadixTree
        self.zones.insert(zone_tuple, None)

    def get_zone(self, zone_name: str) -> Optional[DNSZone]:
        zone_tuple = self.get_reverse_tuple(zone_name)
        return self.zones.search(zone_tuple)

    def query(self, name: str, record_type: RecordType) -> Sequence[DNSRecord]:
        if not name.endswith("."):
            name += "."
        zone_tuple = self.get_zone_for_name(name)
        if not zone_tuple:
            return ()
        zone = self.zones.search(zone_tuple)
        return zone.get_records(name, record_type) if zone is not None else ()

    def get_zone_for_name(self, name: str) -> Optional[Tuple[str, ...]]:
        labels = self.get_reverse_tuple(name)
        result = self.zones.find_prefix(labels)
        return result[0] if result else None

    @staticmethod
    def get_reverse_tuple(zone_name: str) -> Tuple[str, ...]:
        return tuple(zone_name.strip(".").split("."))[::-1]
