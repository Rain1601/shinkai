type ShinkaiMarkProps = {
  size?: number;
  strokeWidth?: number;
};

/**
 * Shinkai (深海) mark — a depth sounder.
 *
 * Anthropic's wordmark sits with a sunburst mark that radiates outward.
 * Shinkai is its mirror: a sounding-line descending into depth. The mark
 * is an inverted triangle outline with three depth tics inside that taper
 * toward a single bottom dot — the way a nautical chart marks descent.
 *
 * Single stroke, ``currentColor``, no fills. Renders cleanly at 16px
 * (sidebar mark) all the way up to 96px (about page).
 */
export function ShinkaiMark({ size = 18, strokeWidth = 1.4 }: ShinkaiMarkProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 28 28"
      fill="none"
      role="img"
      aria-label="shinkai"
    >
      <path
        d="M5 7 L23 7 L14 23 Z"
        stroke="currentColor"
        strokeWidth={strokeWidth}
        strokeLinejoin="round"
        fill="none"
      />
      <line
        x1="9"
        y1="12"
        x2="19"
        y2="12"
        stroke="currentColor"
        strokeWidth={strokeWidth * 0.7}
        strokeLinecap="round"
      />
      <line
        x1="11"
        y1="16"
        x2="17"
        y2="16"
        stroke="currentColor"
        strokeWidth={strokeWidth * 0.7}
        strokeLinecap="round"
      />
      <circle cx="14" cy="20.5" r={strokeWidth * 0.85} fill="currentColor" />
    </svg>
  );
}
