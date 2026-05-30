const S = (size, sw) => ({
  width: size, height: size, viewBox: "0 0 24 24", fill: "none",
  stroke: "currentColor", strokeWidth: sw ?? (size <= 18 ? 2 : 1.6),
  strokeLinecap: "round", strokeLinejoin: "round",
});

export const IconHome      = ({ size = 18 }) => <svg {...S(size)}><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>;
export const IconList      = ({ size = 18 }) => <svg {...S(size)}><line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/></svg>;
export const IconDoc       = ({ size = 18 }) => <svg {...S(size)}><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>;
export const IconTruck     = ({ size = 18 }) => <svg {...S(size)}><rect x="1" y="3" width="15" height="13"/><polygon points="16 8 20 8 23 11 23 16 16 16 16 8"/><circle cx="5.5" cy="18.5" r="2.5"/><circle cx="18.5" cy="18.5" r="2.5"/></svg>;
export const IconScan      = ({ size = 18 }) => <svg {...S(size)}><polyline points="23 7 23 1 17 1"/><line x1="16" y1="8" x2="23" y2="1"/><polyline points="1 17 1 23 7 23"/><line x1="8" y1="16" x2="1" y2="23"/><line x1="21" y1="12" x2="3" y2="12"/></svg>;
export const IconPackage   = ({ size = 18 }) => <svg {...S(size)}><line x1="16.5" y1="9.4" x2="7.5" y2="4.21"/><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><polyline points="3.27 6.96 12 12.01 20.73 6.96"/><line x1="12" y1="22.08" x2="12" y2="12"/></svg>;
export const IconClipboard = ({ size = 18 }) => <svg {...S(size)}><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/><rect x="8" y="2" width="8" height="4" rx="1" ry="1"/></svg>;
export const IconUpload    = ({ size = 32 }) => <svg {...S(size, 1.6)}><polyline points="16 16 12 12 8 16"/><line x1="12" y1="12" x2="12" y2="21"/><path d="M20.39 18.39A5 5 0 0 0 18 9h-1.26A8 8 0 1 0 3 16.3"/></svg>;
export const IconRefresh   = ({ size = 14 }) => <svg {...S(size)}><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>;
export const IconPlus      = ({ size = 14 }) => <svg {...S(size, 2.5)}><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>;
export const IconArrow     = ({ size = 14 }) => <svg {...S(size)}><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>;
export const IconLogout    = ({ size = 16 }) => <svg {...S(size)}><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>;
export const IconDownload  = ({ size = 14 }) => <svg {...S(size)}><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>;
export const IconStore     = ({ size = 18 }) => <svg {...S(size)}><path d="M3 9l1.5-5h15L21 9"/><path d="M4 9v10a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1V9"/><path d="M3 9h18"/><path d="M8 9v3a2 2 0 1 1-4 0"/><path d="M12 9v3a2 2 0 1 1-4 0"/><path d="M16 9v3a2 2 0 1 1-4 0"/><path d="M20 9v3a2 2 0 1 1-4 0"/></svg>;
export const IconSparkles  = ({ size = 18 }) => <svg {...S(size)}><path d="M12 3l1.9 4.6L18.5 9.5l-4.6 1.9L12 16l-1.9-4.6L5.5 9.5l4.6-1.9z"/><path d="M19 14l.8 2 .2.0L22 17l-2 .8-.8 2-.8-2L16 17l2-.8z"/></svg>;
export const IconCheck     = ({ size = 16 }) => <svg {...S(size)}><polyline points="20 6 9 17 4 12"/></svg>;
export const IconFilePdf   = ({ size = 18 }) => <svg {...S(size)}><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><path d="M9 13h1.5a1.5 1.5 0 0 1 0 3H9zM9 13v6"/><path d="M14 13v6h1a2 2 0 0 0 2-2v-2a2 2 0 0 0-2-2z"/></svg>;
export const IconAlert     = ({ size = 16 }) => <svg {...S(size)}><path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>;
