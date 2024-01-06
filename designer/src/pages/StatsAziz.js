import {useDispatch, useSelector} from "react-redux";
import {ChartsContainer, StatsContainer} from "../components";
import {useEffect} from "react";

import React, {PureComponent} from 'react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer, Area, AreaChart
} from 'recharts';

const countableData = [
  {
    name: '20.11.2020',
    fall: 120,
    armsUp: 187,
    frontBending: 66,
  },
  {
    name: '21.11.2020',
    fall: 77,
    armsUp: 250,
    frontBending: 99,
  },
  {
    name: '22.11.2020',
    fall: 127,
    armsUp: 189,
    frontBending: 164,
  },
  {
    name: '23.11.2020',
    fall: 41,
    armsUp: 67,
    frontBending: 54,
  },
  {
    name: '24.11.2020',
    fall: 204,
    armsUp: 174,
    frontBending: 111,
  },

];

const periodicData = [
  {
    name: '20.11.2020',
    NoHelmet: 120,
    NoJacket: 187,
  },
  {
    name: '21.11.2020',
    NoHelmet: 77,
    NoJacket: 250,
  },
  {
    name: '22.11.2020',
    NoHelmet: 127,
    NoJacket: 189,
  },
  {
    name: '23.11.2020',
    NoHelmet: 41,
    NoJacket: 67,
  },
  {
    name: '24.11.2020',
    NoHelmet: 204,
    NoJacket: 174,
  },

];

const StatsAziz = () => {


  return (
      <div style={{width: '100%', height: 300}}>

        <ResponsiveContainer width="100%" height="100%">

          <BarChart
              width={500}
              height={300}
              data={countableData}
              margin={{
                top: 5,
                right: 30,
                left: 20,
                bottom: 5,
              }}
          >
            <CartesianGrid strokeDasharray="3 3"/>
            <XAxis dataKey="name"/>
            <YAxis/>
            <Tooltip/>
            <Legend/>
            <Bar dataKey="armsUp" fill="#3F4E4F" background={{fill: '#eee'}}/>
            <Bar dataKey="fall" fill="#00ADB5"  background={{fill: '#eee'}}/>
            <Bar dataKey="frontBending" fill="#222831"  background={{fill: '#eee'}}/>

          </BarChart>
        </ResponsiveContainer>
        <ResponsiveContainer width="100%" height="100%">

          <BarChart
              width={500}
              height={300}
              data={periodicData}
              margin={{
                top: 5,
                right: 30,
                left: 20,
                bottom: 5,
              }}
          >
            <CartesianGrid strokeDasharray="3 3"/>
            <XAxis dataKey="name"/>
            <YAxis/>
            <Tooltip/>
            <Legend/>
            <Bar dataKey="NoHelmet" fill="#3F4E4F" background={{fill: '#eee'}}/>
            <Bar dataKey="NoJacket" fill="#00ADB5"  background={{fill: '#eee'}}/>

          </BarChart>
        </ResponsiveContainer>


      </div>

  );
};

export default StatsAziz;