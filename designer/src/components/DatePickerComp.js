// DateRangePickerComp.js
import React, { useState } from "react";
import DatePicker from "react-datepicker";
import "react-datepicker/dist/react-datepicker.css";
import "./datePicker.css";

const DateRangePickerComp = ({ onApply }) => {
  const [startDate, setStartDate] = useState(null);
  const [endDate, setEndDate] = useState(null);

  const applyDates = () => {
    if (startDate && endDate) {
      onApply(startDate.getTime(), endDate.getTime());
    }
  };

  return (
      <div className="date-range-picker">
        <DatePicker
            selected={startDate}
            onChange={(date) => setStartDate(date)}
            selectsStart
            startDate={startDate}
            endDate={endDate}
            dateFormat="dd/MM/yyyy"
            placeholderText="Start Date"
            className="date-picker-input"
        />
        <DatePicker
            selected={endDate}
            onChange={(date) => setEndDate(date)}
            selectsEnd
            startDate={startDate}
            endDate={endDate}
            minDate={startDate}
            dateFormat="dd/MM/yyyy"
            placeholderText="End Date"
            className="date-picker-input"
        />
        <button onClick={applyDates} className="apply-button">
          Apply
        </button>
      </div>
  );
};

export default DateRangePickerComp;
