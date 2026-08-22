// Cooling subsystem module
// Fan curve management and control logic

pub mod controller;
pub mod curves;

pub use controller::CoolingController;
pub use curves::FanCurve;
