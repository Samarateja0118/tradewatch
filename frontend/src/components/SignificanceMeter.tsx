/**
 * Significance 1-5 as a five-segment ordinal meter.
 *
 * Magnitude, so a sequential ramp in one hue rather than five different colours:
 * brighter means more consequential, and the reading survives colourblindness
 * because it is lightness doing the work, not hue. Steps come from the blue
 * ramp's 600→200 band and were validated against this surface — monotone
 * lightness, visible gaps between steps, and the dimmest step still clearing
 * 2:1 against the background.
 *
 * The number is written out beside it. A meter alone would make the reader count
 * segments, and colour is never the only carrier of a value.
 */
const STEPS = ["#184f95", "#256abf", "#3987e5", "#6da7ec", "#9ec5f4"];

export function SignificanceMeter({ value }: { value: number }) {
  return (
    <span className="sig" title={`Significance ${value} of 5`}>
      <span className="sig__bars" aria-hidden="true">
        {[1, 2, 3, 4, 5].map((step) => (
          <span
            key={step}
            className="sig__bar"
            style={{
              // Filled segments take the ramp step for this document's rating, so
              // a 5 reads brighter than a 3 at a glance across a whole list.
              background: step <= value ? STEPS[value - 1] : "var(--line)",
              height: `${5 + step * 2}px`,
            }}
          />
        ))}
      </span>
      <span className="sig__num">{value}</span>
      <span className="visually-hidden">significance {value} of 5</span>
    </span>
  );
}
