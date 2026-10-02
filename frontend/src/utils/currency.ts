/**
 * Centralized Indian Rupee (₹) Currency Formatter.
 *
 * Formats numerical values using the Indian numbering system:
 * e.g. 1299 -> ₹1,299
 *      10999 -> ₹10,999
 *      124999 -> ₹1,24,999
 */
export function formatINR(value: number | null | undefined): string {
  if (value === null || value === undefined || isNaN(value)) {
    return '₹0';
  }

  const hasFractions = value % 1 !== 0;

  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    currencyDisplay: 'symbol',
    minimumFractionDigits: hasFractions ? 2 : 0,
    maximumFractionDigits: 2,
  }).format(value);
}
