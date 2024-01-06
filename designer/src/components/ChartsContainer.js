import React, {useEffect, useState} from 'react';
import BarChart from './BarChart';
import AreaChart from './AreaChart';
import Wrapper from '../assets/wrappers/ChartsContainer';
import DateRangePickerComp from "./DatePickerComp";

const ChartsContainer = () => {
  const [barChart, setBarChart] = useState(true);
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(false);

  const fetchData = async (startDate, endDate) => {
    setLoading(true);
    try {
      const response = await fetch(`http://localhost:8080/event/countable-events/${startDate}/${endDate}`);
      const jsonData = await response.json();
      setData(jsonData);
    } catch (error) {
      console.error('Error fetching data:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData(1640466000000, 1704548630000); // Fetch initial data
  }, []);

  return (
      <Wrapper>
        <h4>Total Violence History By Days</h4>
        <button type='button' onClick={() => setBarChart(!barChart)}>
          {barChart ? 'Area Chart' : 'Bar Chart'}
        </button>
        <DateRangePickerComp onApply={fetchData} />
        {loading ? (
            <p>Loading...</p>
        ) : data.length === 0 ? (
            <h1>No data available</h1>
        ) : (
            barChart ? <BarChart data={data} /> : <AreaChart data={data} />
        )}
      </Wrapper>
  );
};

export default ChartsContainer;