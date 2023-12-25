import React, { useState } from 'react';

import BarChart from './BarChart';
import AreaChart from './AreaChart';
import Wrapper from '../assets/wrappers/ChartsContainer';
import { useSelector } from 'react-redux';
const ChartsContainer = () => {
    const [barChart, setBarChart] = useState(true);
    const { results: data } = useSelector((store) => store.allCars);
    return (
        <Wrapper>
            <h4>Total Violance History By Days</h4>
            <button type='button' onClick={() => setBarChart(!barChart)}>
                {barChart ? 'Area Chart' : 'Bar Chart'}
            </button>
            {barChart ? <BarChart data={data} /> : <AreaChart data={data} />}
        </Wrapper>
    );
};
export default ChartsContainer;