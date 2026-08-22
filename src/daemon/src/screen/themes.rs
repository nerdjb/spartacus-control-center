// LCD theme renderers — four layouts recreating classic DeepCool-style
// dashboards, drawn live from real telemetry.
//
//   cards        - dark purple, white stat cards (reference screenshot 2)
//   cards-light  - lavender variant with larger cards (screenshot 3)
//   colorful     - rainbow multi-panel dashboard (screenshot 1)
//   rings        - pastel ring gauges + big clock (screenshot 4)

use super::draw::Canvas;
use super::themes_cards;
use super::themes_fx;
use super::Metrics;
use fontdue::Font;

pub fn cards(c: &mut Canvas, m: &Metrics, font: &Font) {
    themes_cards::cards(c, m, font)
}

pub fn cards_light(c: &mut Canvas, m: &Metrics, font: &Font) {
    themes_cards::cards_light(c, m, font)
}

pub fn colorful(c: &mut Canvas, m: &Metrics, font: &Font) {
    themes_fx::colorful(c, m, font)
}

pub fn rings(c: &mut Canvas, m: &Metrics, font: &Font) {
    themes_fx::rings(c, m, font)
}
