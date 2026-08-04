import React, {useEffect, useState} from 'react';
import BarChart from '../components/BarChart';
import LineChart from '../components/LineChartComponent';
import Wrapper from '../assets/wrappers/ChartsContainer';
import DateRangePickerComp from "../components/DatePickerComp";
import AreaChart from '../components/AreaChart';
import {PieChartComponent} from "../components";
import {useSelector} from "react-redux";
import customFetch from "../util/axios";

const ChartsContainer = () => {
  const [data, setData] = useState([]);
  const [pieChartData, setPieChartData] = useState([]);
  const [periodicEventsData, setPeriodicEventsData] = useState([]);
  const [loading, setLoading] = useState(false);
  const [countableEventsChartType, setCountableEventsChartType] = useState(
      'bar');
  const [periodicEventsChartType, setPeriodicEventsChartType] = useState(
      'bar');

  const keysAndColorsCountableBar = [
    {key: 'fall', color: '#B799FF'},
    {key: 'armsUp', color: '#ACBCFF'},
    {key: 'frontBending', color: '#AEE2FF'},
  ];

  const keysAndColorsPeriodicEventsBar = [
    {key: 'noHelmet', color: '#B799FF'},
    {key: 'noJacket', color: '#ACBCFF'},
  ];
  const keysAndColorsCountableEventsLineChart = [
    {key: 'fall', stroke: '#1D2B53', fill: '#B799FF'},
    {key: 'armsUp', stroke: '#7E2553', fill: '#ACBCFF'},
    {key: 'frontBending', stroke: '#525CEB', fill: '#AEE2FF'},
  ];

  const keysAndColorsPeriodicEventsLineChart = [
    {key: 'noHelmet', stroke: '#1D2B53', fill: '#B799FF'},
    {key: 'noJacket', stroke: '#7E2553', fill: '#ACBCFF'},
  ];

  const keysAndColorsCountableAreaChart = [
    {key: 'fall', stroke: '#92C7CF', fill: '#B799FF', strokeDasharray: '5 5'},
    {key: 'armsUp', stroke: '#AAD7D9', fill: '#ACBCFF', strokeDasharray: '5 5'},
    {
      key: 'frontBending',
      stroke: '#86B6F6',
      fill: '#AEE2FF',
      strokeDasharray: '5 5'
    },
  ];

  const keysAndColorsPeriodicEventsAreaChart = [
    {
      key: 'noHelmet',
      stroke: '#92C7CF',
      fill: '#B799FF',
      strokeDasharray: '5 5'
    },
    {
      key: 'noJacket',
      stroke: '#86B6F6',
      fill: '#AEE2FF',
      strokeDasharray: '5 5'
    },
  ];
  const renderCountableEventsChart = () => {
    switch (countableEventsChartType) {
      case 'line':
        return <LineChart data={data}
                          keysAndColors={keysAndColorsCountableEventsLineChart}
                          yAxisTitle="Total Count Of Events"/>;
      case 'bar':
        return <BarChart data={data} keysAndColors={keysAndColorsCountableBar}
                         yAxisTitle="Total Count Of Events"/>;
      case 'area':
        return <AreaChart data={data}
                          keysAndColors={keysAndColorsCountableAreaChart}
                          yAxisTitle="Total Count Of Events"/>;
      case 'pie':
        return <PieChartComponent pieChartData={pieChartData}
                                  yAxisTitle="Percentage Count Of Events"/>;
      default:
        return <PieChartComponent pieChartData={pieChartData}
                                  yAxisTitle="Percentage Count Of Events"/>;
    }
  };

  const renderPeriodicEventsChart = () => {
    switch (periodicEventsChartType) {
      case 'line':
        return <LineChart data={periodicEventsData}
                          keysAndColors={keysAndColorsPeriodicEventsLineChart}
                          yAxisTitle="Duration Of Violations (Seconds)"/>;
      case 'bar':
        return <BarChart data={periodicEventsData}
                         keysAndColors={keysAndColorsPeriodicEventsBar}
                         yAxisTitle="Duration Of Violations (Seconds)"/>;
      case 'area':
        return <AreaChart data={periodicEventsData}
                          keysAndColors={keysAndColorsPeriodicEventsAreaChart}
                          yAxisTitle="Duration Of Violations (Seconds)"/>;
      default:
        return <BarChart data={periodicEventsData}
                         keysAndColors={keysAndColorsPeriodicEventsBar}
                         yAxisTitle="Duration Of Violations (Seconds)"/>;
    }
  };

  const {isLoading, user} = useSelector((store) => store.user);

  const fetchCountableEventsData = async (startDate, endDate) => {
    setLoading(true);
    try {
      const response = await customFetch.get(
          `event/countable-events/${startDate}/${endDate}`, {
            headers: {
              Authorization: `Bearer ${user.token}`,
            },
          }
      );
      const jsonData = response.data;
      setData(jsonData);
    } catch (error) {
      console.error('Error fetching data:', error);
    } finally {
      setLoading(false);
    }
  };

  const fetchPeriodicEventsData = async (startDate, endDate) => {
    setLoading(true);
    try {
      const response = await customFetch.get(
          `event/periodic-events/${startDate}/${endDate}`, {
            headers: {
              Authorization: `Bearer ${user.token}`,
            },
          }
      );
      const jsonData = response.data;
      setPeriodicEventsData(jsonData);
    } catch (error) {
      console.error('Error fetching data:', error);
    } finally {
      setLoading(false);
    }
  };

  const fetchPieChartData = async (startDate, endDate) => {
    setLoading(true);
    try {
      const response = await customFetch.get(
          `event/pie-chart-events/${startDate}/${endDate}`, {
            headers: {
              Authorization: `Bearer ${user.token}`,
            },
          }
      );
      const jsonData = response.data;
      setPieChartData(jsonData);
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

    fetchCountableEventsData(oneWeekAgo.getTime(), today.getTime());
    fetchPeriodicEventsData(oneWeekAgo.getTime(), today.getTime());
    fetchPieChartData(oneWeekAgo.getTime(), today.getTime());
  }, []);

  return (
      <Wrapper>
        <h4>Total Countable Events History By Days</h4>
        <div>
          <button type='button'
                  onClick={() => setCountableEventsChartType('bar')}>
            Bar Chart
          </button>
          <button type='button'
                  onClick={() => setCountableEventsChartType('line')}>
            Line Chart
          </button>
          <button type='button'
                  onClick={() => setCountableEventsChartType('area')}>
            Area Chart
          </button>
          <button type='button'
                  onClick={() => setCountableEventsChartType('pie')}>
            Pie Chart
          </button>
        </div>
        <DateRangePickerComp onApply={(startDate, endDate) => {
          if (countableEventsChartType === 'pie') {
            fetchPieChartData(startDate, endDate);
          } else {
            fetchCountableEventsData(startDate, endDate);
          }
        }}/>
        {loading ? (
            <p>Loading...</p>
        ) : data.length === 0 ? (
            <h1>No data available</h1>
        ) : (
            renderCountableEventsChart()
        )}

        <div className={"charts-container-buffer"}>

        </div>

        <h4>Total Duration of Periodic Events History By Days</h4>
        <div>
          <button type='button'
                  onClick={() => setPeriodicEventsChartType('bar')}>
            Bar Chart
          </button>
          <button type='button'
                  onClick={() => setPeriodicEventsChartType('line')}>
            Line Chart
          </button>
          <button type='button'
                  onClick={() => setPeriodicEventsChartType('area')}>
            Area Chart
          </button>
        </div>
        <DateRangePickerComp onApply={fetchPeriodicEventsData}/>
        {loading ? (
            <p>Loading...</p>
        ) : periodicEventsData.length === 0 ? (
            <h1>No data available</h1>
        ) : (
            renderPeriodicEventsChart()
        )}
      </Wrapper>
  );
};

export default ChartsContainer;