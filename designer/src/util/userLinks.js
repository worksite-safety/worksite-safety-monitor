import {MdPayment, MdQueryStats} from 'react-icons/md';
import { ImProfile } from 'react-icons/im';

const links = [

    {
        id: 1,
        text: 'Statistics',
        path: 'statistics',
        icon: <MdQueryStats />,
    },
    {
        id: 2,
        text: 'Reports',
        path: 'reports',
        icon: <MdPayment />,
    },
    {
        id: 3,
        text: 'profile',
        path: 'profile',
        icon: <ImProfile />,
    },
];

export default links;