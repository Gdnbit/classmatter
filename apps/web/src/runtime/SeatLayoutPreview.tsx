import './seat-layout-preview.css'

export function SeatLayoutPreview({ rows, columns }: { rows: unknown; columns: unknown }) {
  if (typeof rows !== 'number' || typeof columns !== 'number' || !Number.isInteger(rows) || !Number.isInteger(columns)
    || rows < 1 || rows > 20 || columns < 1 || columns > 20) return null
  return <section className="seat-layout-preview" aria-label="座位布局预览">
    <p>{rows} 排 × {columns} 座</p>
    <div className="seat-layout-scroll" role="table" aria-label="空座布局">
      {Array.from({ length: rows }, (_, row) => <div role="row" className="seat-layout-row" key={row} style={{ gridTemplateColumns: `repeat(${columns}, minmax(48px, 1fr))` }}>
        {Array.from({ length: columns }, (_, column) => <div role="cell" className="seat-layout-cell" key={column} aria-label={`${row + 1}排${column + 1}座 空座`}>{row + 1}-{column + 1}</div>)}
      </div>)}
    </div>
  </section>
}
