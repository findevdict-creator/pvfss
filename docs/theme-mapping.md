# Theme variable mapping (plan §6.3)

Audited against the compiled `desk.bundle.css` of Frappe **v16.54.0** (1,033 custom properties).
Re-run this audit on every Frappe minor update before production (NFR-11).

| PVFSS token | Frappe v16 variable(s) | Present in v16.54.0 |
|---|---|---|
| `--pvfss-primary` | `--primary`, `--primary-color`, `--btn-primary` | yes |
| `--pvfss-bg-page` | `--bg-color` | yes |
| `--pvfss-bg-surface` | `--fg-color`, `--card-bg`, `--navbar-bg` | yes |
| `--pvfss-bg-subtle` | `--control-bg` | yes |
| `--pvfss-text` | `--text-color`, `--heading-color` | yes |
| `--pvfss-text-muted` | `--text-muted`, `--text-light` | yes |
| `--pvfss-border` / `-strong` | `--border-color`, `--dark-border-color` | yes |
| `--pvfss-font` | `--font-stack` | yes |
| `--pvfss-radius*` | `--border-radius`, `--border-radius-md`, `--border-radius-lg` | yes |
| `--pvfss-sidebar` | `--desk-sidebar-bg` | yes |
| status pills | `--bg-{green,orange,red,blue,gray,purple}`, `--text-on-{…}` | yes |

## The one scoped override

v16 draws sidebar text and hover states with the `--ink-gray-*` and `--surface-gray-*` scales.
To get the dark navy sidebar from the prototype, those variables are re-pointed **inside
`.body-sidebar` only**. No component CSS is replaced, so an upgrade can at worst fall back to the
standard light sidebar.

## Not variables

- Letter Head "PVFSS" and Print Style "PVFSS" are created and kept in sync from
  `pvfss/templates/print/` by `pvfss.setup.branding.apply()` on every migrate, so the source of
  truth is in git (GEN-02) rather than in an exported fixture.
- Logo and favicon in `pvfss/public/images/` are **placeholders** until PVFSS sends its brand
  guide (DQ-01). Replacing the two SVG files is enough.
