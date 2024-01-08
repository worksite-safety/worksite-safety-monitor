import React, {useEffect, useState} from 'react';
import BarChart from './BarChart';
import LineChart from './LineChartComponent';
import Wrapper from '../assets/wrappers/ChartsContainer';
import DateRangePickerComp from "./DatePickerComp";
import AreaChart from './AreaChart';

const ChartsContainer = () => {
  const [barChart, setBarChart] = useState(true);
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(false);
  const [chartType, setChartType] = useState('area');
  const renderChart = () => {
    switch (chartType) {
      case 'line':
        return <LineChart data={data} />;
      case 'bar':
        return <BarChart data={data} />;
      case 'area':
        return <AreaChart data={data} />;
      case 'pie':
        //return <PieChart data={data} />;
      default:
        return <BarChart data={data} />;
    }
  };
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
    const today = new Date();
    const oneWeekAgo = new Date(today.getTime() - 7 * 24 * 60 * 60 * 1000);

    oneWeekAgo.setHours(0, 0, 1);
    today.setHours(23, 59, 59);

    fetchData(oneWeekAgo.getTime(), today.getTime());
  }, []);

  return (
      <Wrapper>
        <h4>Total Countable Events History By Days</h4>
        <div>
          <button type='button' onClick={() => setChartType('bar')}>
            Bar Chart
          </button>
          <button type='button' onClick={() => setChartType('line')}>
            Line Chart
          </button>
          <button type='button' onClick={() => setChartType('area')}>
            Area Chart
          </button>
          <button type='button' onClick={() => setChartType('pie')}>
            Pie Chart
          </button>
        </div>
        <DateRangePickerComp onApply={fetchData}/>
        {loading ? (
            <p>Loading...</p>
        ) : data.length === 0 ? (
            <h1>No data available</h1>
        ) : (
            renderChart()
        )}
      </Wrapper>
  );
};

export default ChartsContainer;