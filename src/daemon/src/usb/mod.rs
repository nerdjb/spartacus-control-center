// USB subsystem module
// Handles communication with LCD Display (0x3633:0x0027) and Controller (0x3633:0x002D)

pub mod controller;
pub mod lcd;
pub mod monitor;

pub use controller::ControllerDevice;
pub use lcd::LCDDevice;

pub const DEEPCOOL_VENDOR_ID: u16 = 0x3633;
pub const LCD_PRODUCT_ID: u16 = 0x0027;
pub const CONTROLLER_PRODUCT_ID: u16 = 0x002D;

// LCD Display specifications
pub const LCD_WIDTH: u16 = 480;
pub const LCD_HEIGHT: u16 = 480;
pub const LCD_BPP: u16 = 3; // 24-bit RGB
pub const LCD_FRAME_SIZE: usize = (LCD_WIDTH as usize) * (LCD_HEIGHT as usize) * (LCD_BPP as usize);

// USB timeouts
pub const USB_TIMEOUT_MS: u64 = 2000;

// LCD Display (3633:0027) endpoints
//   Host -> device: bulk 0x02 (image stream), bulk 0x04 (control)
//   Device -> host: 0x81 / 0x83 (present, unused)
pub const LCD_EP_IMAGE_OUT: u8 = 0x02;
pub const LCD_EP_CONTROL_OUT: u8 = 0x04;

// Linker Controller (3633:002D) endpoints
//   Host -> device: interrupt 0x01 (control report)
//   Device -> host: interrupt 0x81 (status report)
pub const LINKER_EP_CONTROL_OUT: u8 = 0x01;
pub const LINKER_EP_STATUS_IN: u8 = 0x81;

/// Additive 16-bit checksum (display control + image), little-endian on the wire.
pub fn sum16(data: &[u8]) -> u16 {
    data.iter().fold(0u32, |acc, &b| acc.wrapping_add(b as u32)) as u16
}

/// Additive 8-bit checksum (Linker report).
pub fn sum8(data: &[u8]) -> u8 {
    data.iter().fold(0u32, |acc, &b| acc.wrapping_add(b as u32)) as u8
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn sum16_matches_spec_vectors() {
        // Session Start: sum of AA 2E 05 01 + 40 zeros = 0xDE
        let pkt = [0xAAu8, 0x2E, 0x05, 0x01];
        assert_eq!(sum16(&pkt), 0x00DE);
        // Session Stop = 0xDD
        let pkt = [0xAAu8, 0x2E, 0x05, 0x00];
        assert_eq!(sum16(&pkt), 0x00DD);
        // Config upright 100%: AA+2E+04+01+64 = 0x141
        let pkt = [0xAAu8, 0x2E, 0x04, 0x01, 0x64];
        assert_eq!(sum16(&pkt), 0x0141);
    }

    #[test]
    fn telemetry_template_checksum_matches() {
        let pkt = crate::usb::lcd::telemetry_packet(86, 100);
        assert_eq!(&pkt[44..46], &[0xEF, 0x02]);
        assert_eq!(sum16(&pkt[0..44]), 0x02EF);
    }
}

#[derive(Debug, Clone)]
pub struct USBDeviceInfo {
    pub vendor_id: u16,
    pub product_id: u16,
    pub serial_number: String,
    pub manufacturer: String,
    pub product_name: String,
}
