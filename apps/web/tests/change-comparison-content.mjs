// Exact business text and positions, independent of block-layout line breaks.
export function comparisonContent(side) {
  return side.evaluate(node => ({
    heading: node.querySelector('h3')?.textContent,
    empty: node.querySelector('.change-empty')?.textContent ?? null,
    fields: [...node.querySelectorAll('dl > div')].map(field => ({
      label: field.querySelector('dt')?.textContent,
      value: field.querySelector('dd')?.textContent,
    })),
    seats: [...node.querySelectorAll('[role="cell"]')].map(cell => ({
      position: cell.querySelector('small')?.textContent,
      student: cell.querySelector('span')?.textContent,
      accessible: cell.getAttribute('aria-label'),
    })),
  }));
}
