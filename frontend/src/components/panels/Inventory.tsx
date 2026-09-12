/** Interceptor inventory as pips plus a count. */
export function Inventory({
  count,
  capacity,
}: {
  count: number;
  capacity: number;
}) {
  return (
    <span aria-label={`${count} of ${capacity} interceptors`}>
      <span className="c-pips" aria-hidden="true">
        {Array.from({ length: capacity }, (_, i) => (
          <span key={i} className={`c-pip${i < count ? "" : " is-spent"}`} />
        ))}
      </span>
      <small>
        {count} / {capacity}
      </small>
    </span>
  );
}
