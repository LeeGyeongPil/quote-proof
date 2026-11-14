# Spec

The exporter writes a header row first, then one row per record, and finally a checksum line that
covers every row before it. Consumers must reject files whose checksum does not match.
