import React from 'react';
import { Outlet } from 'react-router-dom';
import Sidebar from './Sidebar';
import Header from './Header';
import CommandPalette from '../CommandPalette';

const AppShell = () => {
    return (
        <div className="flex h-screen overflow-hidden bg-background font-sans text-foreground">
            <a
                href="#main-content"
                className="sr-only focus:not-sr-only focus:absolute focus:z-[100] focus:top-2 focus:left-2 focus:rounded-md focus:bg-card focus:px-4 focus:py-2 focus:text-sm focus:font-medium focus:shadow-lg focus:ring-2 focus:ring-ring"
            >
                Skip to main content
            </a>
            <CommandPalette />
            <Sidebar />

            <main className="flex-1 flex flex-col min-w-0">
                <Header />

                <div id="main-content" tabIndex={-1} className="flex-1 overflow-auto focus:outline-none">
                    <div className="mx-auto max-w-[1440px] p-6 lg:p-8">
                        <Outlet />
                    </div>
                </div>
            </main>
        </div>
    );
};

export default AppShell;
