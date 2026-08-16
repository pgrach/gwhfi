// The real Heat21 "Node" mark, pulled from heat21.co.uk's own markup: an
// octagonal enclosure with three bars of warmth radiating from it. Single
// line weight, single colour (currentColor), per brand spec.
export function Heat21Mark({ className }: { className?: string }) {
    return (
        <svg viewBox="0 0 124 64" fill="none" xmlns="http://www.w3.org/2000/svg" className={className}>
            <polygon
                points="56.02,41.95 41.95,56.02 22.05,56.02 7.98,41.95 7.98,22.05 22.05,7.98 41.95,7.98 56.02,22.05"
                fill="none"
                stroke="currentColor"
                strokeWidth="9"
                strokeLinejoin="miter"
            />
            <rect x="72" y="6" width="9" height="52" rx="1.5" fill="currentColor" />
            <rect x="90.5" y="15" width="9" height="34" rx="1.5" fill="currentColor" />
            <rect x="109" y="23" width="9" height="18" rx="1.5" fill="currentColor" />
        </svg>
    )
}
