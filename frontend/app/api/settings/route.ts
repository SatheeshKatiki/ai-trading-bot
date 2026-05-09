import { NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';

// Force dynamic rendering
export const dynamic = 'force-dynamic';

export async function GET() {
  try {
    const filePath = path.join(process.cwd(), '..', 'trading-system', 'settings.json');
    
    if (!fs.existsSync(filePath)) {
      return NextResponse.json({ error: 'Settings file not found' }, { status: 404 });
    }
    
    const fileContent = fs.readFileSync(filePath, 'utf8');
    const data = JSON.parse(fileContent);
    
    return NextResponse.json(data);
  } catch (error) {
    console.error('Failed to read settings file:', error);
    return NextResponse.json({ error: 'Failed to read settings file' }, { status: 500 });
  }
}

export async function POST(request: Request) {
  try {
    const data = await request.json();
    const filePath = path.join(process.cwd(), '..', 'trading-system', 'settings.json');
    
    // Read existing settings to merge
    let existingData = {};
    if (fs.existsSync(filePath)) {
      const fileContent = fs.readFileSync(filePath, 'utf8');
      existingData = JSON.parse(fileContent);
    }
    
    // Merge new data with existing data
    const updatedData = { ...existingData, ...data };
    
    // Save back to file with pretty print
    fs.writeFileSync(filePath, JSON.stringify(updatedData, null, 4));
    
    return NextResponse.json({ success: true, message: 'Settings saved successfully' });
  } catch (error) {
    console.error('Failed to save settings:', error);
    return NextResponse.json({ error: 'Failed to save settings' }, { status: 500 });
  }
}
