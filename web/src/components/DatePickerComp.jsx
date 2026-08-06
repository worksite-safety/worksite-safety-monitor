import React, { useEffect, useState } from "react";
import DatePicker from "react-datepicker";
import "react-datepicker/dist/react-datepicker.css";
import "./datePicker.css";
import {toast} from "react-toastify";
// Was @mui/icons-material/Email. MdEmail is the same Material "email" glyph
// (identical path data, 24x24 viewBox), but react-icons sizes to 1em while
// MUI's SvgIcon was a fixed 1.5rem -- and this button never sets a font-size,
// so 1em would collapse to the UA button default (~13px). ICON_SIZE pins the
// rendered size to what MUI drew.
import {MdEmail} from 'react-icons/md';
import {useSelector} from "react-redux";
import customFetch from "../util/axios";

// MUI SvgIcon's default fontSize="medium" resolved to 1.5rem (24px at the
// app's 100% root font size). Keep it in rem so it still tracks a user's
// browser font-size preference the way the MUI icon did.
const ICON_SIZE = "1.5rem";

const DateRangePickerComp = ({ onApply, applyButtonLabel, clearButtonLabel }) => {
  const [startDate, setStartDate] = useState(null);
  const [endDate, setEndDate] = useState(null);
  const [loading, setLoading] = useState(false); // Added loading state
  const {isLoading, user} = useSelector((store) => store.user);

  const applyDates = () => {
    if (startDate && endDate) {
      onApply(startDate.getTime(), endDate.getTime());
    }
  };
  const applyReportSend = async () => {
    if (startDate && endDate) {
      setLoading(true);
      try {
        const response = await customFetch.post(
            `/event/sendPdfEmail/${startDate.getTime()}/${endDate.getTime()}/${user.email}`,
            {}
        );
        if (response.status === 200) {
          toast.success("Report sent successfully!");
        } else {
          toast.error("Failed to send report.");
        }
      } catch (error) {
        console.error("Error sending report:", error);
        toast.error("Error sending report.");
      } finally {
        setLoading(false);
      }
    }
  };

  useEffect(() => {
    const oneWeekAgo = new Date();
    oneWeekAgo.setDate(oneWeekAgo.getDate() - 7);

    const today = new Date();

    setStartDate(oneWeekAgo);
    setEndDate(today);
  }, []);

  const clearDates = () => {
    const oneWeekAgo = new Date();
    oneWeekAgo.setDate(oneWeekAgo.getDate() - 7);

    const today = new Date();
    setStartDate(oneWeekAgo);
    setEndDate(today);
  };

  const handleStartDateChange = (date) => {

    if (!endDate || date < endDate) {
      setStartDate(date);

    }
  };

  const handleEndDateChange = (date) => {

    if (!startDate || date > startDate) {
      setEndDate(date);

    }
  };

  return (
      <div className="date-range-picker">
        <DatePicker
            selected={startDate}
            onChange={handleStartDateChange}
            selectsStart
            startDate={startDate}
            endDate={endDate}
            dateFormat="dd/MM/yyyy"
            placeholderText="Start Date"
            className="date-picker-input"
            minDate={new Date("01/01/2023")}
            maxDate={new Date(Date.now() - 24 * 60 * 60 * 1000)}
        />
        <DatePicker
            selected={endDate}
            onChange={handleEndDateChange}
            selectsEnd
            startDate={startDate}
            endDate={endDate}
            minDate={startDate}
            dateFormat="dd/MM/yyyy"
            placeholderText="End Date"
            className="date-picker-input"
            maxDate={new Date()}
        />
        {applyButtonLabel && applyButtonLabel.includes("Send Report") ? (
            <button
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  marginRight: 10,
                  backgroundColor: "#4CAF50",
                  color: "white",
                  border: "none",
                  borderRadius: "5px",
                  cursor: loading ? "not-allowed" : "pointer", // Disable button during loading
                }}
                onClick={applyReportSend}
                disabled={loading} // Disable button during loading
            >
              <MdEmail style={{fontSize: ICON_SIZE}} aria-hidden="true" focusable="false"/>
              Send Report
            </button>
        ) : (
            <button onClick={applyDates} className="apply-button">
              {applyButtonLabel || "Apply"}
            </button>
        )}
        <button onClick={clearDates} className="apply-button">
          {clearButtonLabel || "Clear"}
        </button>
      </div>
  );
};

export default DateRangePickerComp;
