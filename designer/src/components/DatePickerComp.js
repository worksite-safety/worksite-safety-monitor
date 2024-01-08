import React, { useEffect, useState } from "react";
import DatePicker from "react-datepicker";
import "react-datepicker/dist/react-datepicker.css";
import "./datePicker.css";
import {toast} from "react-toastify";

const DateRangePickerComp = ({ onApply }) => {
  const [startDate, setStartDate] = useState(null);
  const [endDate, setEndDate] = useState(null);

  const applyDates = () => {
    if (startDate && endDate) {
      onApply(startDate.getTime(), endDate.getTime());
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
        <button onClick={applyDates} className="apply-button">
          Apply
        </button>
        <button onClick={clearDates} className="apply-button">
          Clear
        </button>
      </div>
  );
};

export default DateRangePickerComp;
