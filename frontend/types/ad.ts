// Mirrors backend/schemas/ad.py (AdResponse). Home-page promotional content
// shown to guests; managed by admins in the Studio panel (Phase 10).

export interface Ad {
  id:         string   // UUID
  title:      string
  body:       string | null
  image_url:  string | null
  link_url:   string | null
  cta_label:  string | null
  sort_order: number
}
