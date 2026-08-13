/** Display-only IPv4 masking: hide the last two octets (e.g. 10.20.30.40 → 10.20.x.x). */

const IPV4_WITH_OPTIONAL_CIDR =
  /^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})(\/\d{1,2})?$/;

export function maskIpv4LastTwoOctets(value: string): string {
  const trimmed = value.trim();
  if (!trimmed) {
    return trimmed;
  }

  const match = trimmed.match(IPV4_WITH_OPTIONAL_CIDR);
  if (!match) {
    return trimmed;
  }

  return `${match[1]}.${match[2]}.x.x${match[5] ?? ""}`;
}

/** Mask each IPv4 token in a comma/space/semicolon-separated list. */
export function maskIpDisplayValue(value: string): string {
  const trimmed = value.trim();
  if (!trimmed) {
    return trimmed;
  }

  return trimmed
    .split(/([,;\s]+)/)
    .map((part) => {
      if (/^[,;\s]+$/.test(part)) {
        return part;
      }
      return maskIpv4LastTwoOctets(part);
    })
    .join("");
}
